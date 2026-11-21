"""Controlled Terraform plan/apply lifecycle for Milestone 7."""

import hashlib
import json
import os
import re
import subprocess
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set
from uuid import UUID

from sqlalchemy.orm import Session

from ..core.config import settings
from ..enums import (
    TerraformExecutionEventType,
    TerraformExecutionState,
    TerraformPlanAction,
)
from ..models import TerraformExecution, TerraformExecutionEvent
from .services import ComplianceEngine
from .terraform_generator import TerraformGenerator


class TerraformExecutionError(ValueError):
    """Actionable lifecycle error with a stable machine-readable code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class TerraformCommandRunner:
    """Execute only argument-array Terraform commands without a shell."""

    def run(
        self,
        arguments: List[str],
        cwd: Path,
        timeout_seconds: int,
        environment: Optional[Dict[str, str]] = None,
    ) -> dict:
        command_environment = os.environ.copy()
        if environment:
            command_environment.update(environment)
        completed = subprocess.run(
            arguments,
            cwd=str(cwd),
            env=command_environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            shell=False,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "exit_code": completed.returncode,
            "stdout": completed.stdout or "",
            "stderr": completed.stderr or "",
        }


class TerraformExecutionLockManager:
    """Process-local lock boundary that can later be replaced by distributed locking."""

    _guard = threading.Lock()
    _locks: Dict[str, threading.Lock] = {}

    @classmethod
    @contextmanager
    def acquire(cls, workspace_key: str):
        with cls._guard:
            lock = cls._locks.setdefault(workspace_key, threading.Lock())
        if not lock.acquire(blocking=False):
            raise TerraformExecutionError(
                "EXECUTION_LOCKED",
                "Another Terraform operation is active for this architecture version",
            )
        try:
            yield
        finally:
            lock.release()


class TerraformExecutionService:
    """Persist and enforce the non-interactive Terraform execution lifecycle."""

    PLAN_FILENAME = "execution.tfplan"
    _ACTIVE_STATES = {
        TerraformExecutionState.INITIALIZING.value,
        TerraformExecutionState.VALIDATING.value,
        TerraformExecutionState.PLANNING.value,
        TerraformExecutionState.APPLYING.value,
    }
    _REDACTION_PATTERNS = (
        re.compile(
            r"(?i)((?:[\"']?(?:password|secret|token|api[_-]?key|private[_-]?key|connection[_-]?string)[\"']?)"
            r"\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;]+)"
        ),
        re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]+"),
    )

    @classmethod
    def prepare_workspace(
        cls,
        db: Session,
        architecture_id: UUID,
        version_id: UUID,
        compliance_frameworks: Optional[List[str]] = None,
        azure_preflight_id: Optional[UUID] = None,
    ) -> TerraformExecution:
        """Generate Terraform and write it beneath the controlled workspace root."""
        frameworks = sorted(set(compliance_frameworks or []))
        generation = TerraformGenerator.generate(
            db,
            architecture_id,
            version_id,
            intelligence_mode="AZURE_VALIDATED" if azure_preflight_id else "STATIC_ONLY",
            azure_preflight_id=azure_preflight_id,
        )
        execution = TerraformExecution(
            architecture_id=architecture_id,
            architecture_version_id=version_id,
            state=TerraformExecutionState.PREPARING.value,
            generator_version=generation.get("generator_version"),
            compliance_frameworks=frameworks,
            azure_snapshot_id=generation.get("azure_snapshot_id"),
            azure_preflight_id=generation.get("azure_preflight_id"),
            command_results={},
        )
        db.add(execution)
        db.flush()

        if generation["status"] != "GENERATED":
            execution.state = TerraformExecutionState.FAILED.value
            execution.last_error = "Terraform generation was blocked"
            cls._audit(
                db,
                execution,
                TerraformExecutionEventType.PREPARATION_FAILED.value,
                {"code": "GENERATION_BLOCKED"},
            )
            db.commit()
            db.refresh(execution)
            return execution

        compliance_error = cls._evaluate_compliance_gate(
            db, architecture_id, version_id, frameworks
        )
        if compliance_error:
            execution.state = TerraformExecutionState.FAILED.value
            execution.last_error = compliance_error
            cls._audit(
                db,
                execution,
                TerraformExecutionEventType.PREPARATION_FAILED.value,
                {"code": "COMPLIANCE_BLOCKED"},
            )
            db.commit()
            db.refresh(execution)
            return execution

        generation_hash = cls._generation_hash(
            generation["generator_version"], generation["files"]
        )
        workspace_key = cls._workspace_key(
            architecture_id, version_id, execution.id
        )
        execution.workspace_key = workspace_key
        execution.generation_hash = generation_hash

        try:
            with TerraformExecutionLockManager.acquire(
                cls._architecture_lock_key(architecture_id, version_id)
            ):
                workspace = cls._resolve_workspace(workspace_key)
                workspace.mkdir(parents=True, exist_ok=False)
                cls._write_generated_files(workspace, generation["files"])
        except (OSError, TerraformExecutionError) as error:
            execution.state = TerraformExecutionState.FAILED.value
            execution.last_error = cls._redact_text(str(error))
            cls._audit(
                db,
                execution,
                TerraformExecutionEventType.PREPARATION_FAILED.value,
                {"code": getattr(error, "code", "WORKSPACE_FAILURE")},
            )
            db.commit()
            db.refresh(execution)
            return execution

        execution.state = TerraformExecutionState.GENERATED.value
        cls._audit(
            db,
            execution,
            TerraformExecutionEventType.WORKSPACE_PREPARED.value,
            {
                "generation_hash": generation_hash,
                "file_count": len(generation["files"]),
            },
        )
        db.commit()
        db.refresh(execution)
        return execution

    @classmethod
    def initialize(
        cls,
        db: Session,
        execution_id: UUID,
        runner: Optional[TerraformCommandRunner] = None,
        runtime_environment: Optional[Dict[str, str]] = None,
    ) -> TerraformExecution:
        execution = cls._get_execution(db, execution_id)
        cls._require_state(execution, {TerraformExecutionState.GENERATED.value})
        with cls._execution_lock(execution):
            workspace = cls._workspace(execution)
            execution.state = TerraformExecutionState.INITIALIZING.value
            cls._audit(db, execution, TerraformExecutionEventType.INIT_STARTED.value)
            db.commit()

            version_result = cls._run_command(
                runner,
                [settings.terraform_binary, "version", "-json"],
                workspace,
                "version",
                runtime_environment,
                {0},
            )
            if version_result["status"] != "SUCCEEDED":
                return cls._fail_operation(
                    db,
                    execution,
                    "version",
                    version_result,
                    TerraformExecutionEventType.INIT_FAILED.value,
                )
            execution.terraform_version = cls._parse_terraform_version(
                version_result["stdout"]
            )
            cls._save_command_result(execution, "version", version_result)

            init_result = cls._run_command(
                runner,
                [settings.terraform_binary, "init", "-input=false", "-no-color"],
                workspace,
                "init",
                runtime_environment,
                {0},
            )
            cls._save_command_result(execution, "init", init_result)
            if init_result["status"] != "SUCCEEDED":
                return cls._fail_operation(
                    db,
                    execution,
                    "init",
                    init_result,
                    TerraformExecutionEventType.INIT_FAILED.value,
                )

            execution.state = TerraformExecutionState.INITIALIZED.value
            cls._audit(db, execution, TerraformExecutionEventType.INIT_COMPLETED.value)
            db.commit()
            db.refresh(execution)
            return execution

    @classmethod
    def validate(
        cls,
        db: Session,
        execution_id: UUID,
        runner: Optional[TerraformCommandRunner] = None,
        runtime_environment: Optional[Dict[str, str]] = None,
    ) -> TerraformExecution:
        execution = cls._get_execution(db, execution_id)
        cls._require_state(execution, {TerraformExecutionState.INITIALIZED.value})
        with cls._execution_lock(execution):
            workspace = cls._workspace(execution)
            execution.state = TerraformExecutionState.VALIDATING.value
            cls._audit(
                db, execution, TerraformExecutionEventType.VALIDATION_STARTED.value
            )
            db.commit()
            result = cls._run_command(
                runner,
                [settings.terraform_binary, "validate", "-json", "-no-color"],
                workspace,
                "validate",
                runtime_environment,
                {0},
            )
            cls._save_command_result(execution, "validate", result)
            if result["status"] != "SUCCEEDED":
                return cls._fail_operation(
                    db,
                    execution,
                    "validate",
                    result,
                    TerraformExecutionEventType.VALIDATION_FAILED.value,
                )
            execution.state = TerraformExecutionState.VALIDATED.value
            cls._audit(
                db, execution, TerraformExecutionEventType.VALIDATION_COMPLETED.value
            )
            db.commit()
            db.refresh(execution)
            return execution

    @classmethod
    def create_plan(
        cls,
        db: Session,
        execution_id: UUID,
        runner: Optional[TerraformCommandRunner] = None,
        runtime_environment: Optional[Dict[str, str]] = None,
    ) -> TerraformExecution:
        execution = cls._get_execution(db, execution_id)
        cls._require_state(execution, {TerraformExecutionState.VALIDATED.value})
        with cls._execution_lock(execution):
            if cls._mark_stale_if_needed(db, execution):
                return execution
            compliance_error = cls._evaluate_compliance_gate(
                db,
                execution.architecture_id,
                execution.architecture_version_id,
                execution.compliance_frameworks or [],
            )
            if compliance_error:
                return cls._mark_stale(db, execution, compliance_error)
            execution.state = TerraformExecutionState.PLANNING.value
            cls._audit(db, execution, TerraformExecutionEventType.PLAN_STARTED.value)
            db.commit()

            workspace = cls._workspace(execution)
            plan_result = cls._run_command(
                runner,
                [
                    settings.terraform_binary,
                    "plan",
                    "-input=false",
                    "-no-color",
                    "-detailed-exitcode",
                    f"-out={cls.PLAN_FILENAME}",
                ],
                workspace,
                "plan",
                runtime_environment,
                {0, 2},
            )
            cls._save_command_result(execution, "plan", plan_result)
            if plan_result["status"] != "SUCCEEDED":
                return cls._fail_operation(
                    db,
                    execution,
                    "plan",
                    plan_result,
                    TerraformExecutionEventType.PLAN_FAILED.value,
                )

            plan_path = cls._safe_child(workspace, cls.PLAN_FILENAME)
            if not plan_path.is_file():
                missing_result = {
                    "operation": "plan",
                    "status": "FAILED",
                    "exit_code": plan_result["exit_code"],
                    "stdout": "",
                    "stderr": "Terraform did not create the saved plan artifact",
                    "error_code": "PLAN_ARTIFACT_MISSING",
                }
                cls._save_command_result(execution, "plan", missing_result)
                return cls._fail_operation(
                    db,
                    execution,
                    "plan",
                    missing_result,
                    TerraformExecutionEventType.PLAN_FAILED.value,
                )

            show_result = cls._run_command(
                runner,
                [
                    settings.terraform_binary,
                    "show",
                    "-json",
                    cls.PLAN_FILENAME,
                ],
                workspace,
                "show",
                runtime_environment,
                {0},
            )
            if show_result["status"] != "SUCCEEDED":
                cls._save_command_result(execution, "show", show_result)
                return cls._fail_operation(
                    db,
                    execution,
                    "show",
                    show_result,
                    TerraformExecutionEventType.PLAN_FAILED.value,
                )

            try:
                plan_document = json.loads(show_result["stdout"] or "{}")
                summary = cls.normalize_plan(plan_document)
            except (json.JSONDecodeError, TypeError, ValueError) as error:
                invalid_result = {
                    "operation": "show",
                    "status": "FAILED",
                    "exit_code": show_result["exit_code"],
                    "stdout": "",
                    "stderr": "Terraform plan JSON could not be normalized",
                    "error_code": "PLAN_JSON_INVALID",
                }
                cls._save_command_result(execution, "show", invalid_result)
                return cls._fail_operation(
                    db,
                    execution,
                    "show",
                    invalid_result,
                    TerraformExecutionEventType.PLAN_FAILED.value,
                )

            cls._save_command_result(
                execution,
                "show",
                {
                    **show_result,
                    "stdout": "Terraform plan JSON normalized into plan_summary",
                },
            )

            execution.plan_filename = cls.PLAN_FILENAME
            execution.plan_artifact_hash = cls._hash_file(plan_path)
            execution.plan_summary = summary
            execution.has_destructive_changes = any(
                change["destructive"] for change in summary["changes"]
            )
            execution.state = TerraformExecutionState.AWAITING_APPROVAL.value
            cls._audit(
                db,
                execution,
                TerraformExecutionEventType.PLAN_COMPLETED.value,
                {
                    "plan_artifact_hash": execution.plan_artifact_hash,
                    "has_destructive_changes": execution.has_destructive_changes,
                    "counts": {
                        key: summary[key]
                        for key in ("add", "change", "destroy", "replace", "no_change")
                    },
                },
            )
            db.commit()
            db.refresh(execution)
            return execution

    @classmethod
    def approve_plan(
        cls,
        db: Session,
        execution_id: UUID,
        approved_by: str,
        confirm_destructive: bool = False,
    ) -> TerraformExecution:
        execution = cls._get_execution(db, execution_id)
        cls._require_state(
            execution, {TerraformExecutionState.AWAITING_APPROVAL.value}
        )
        with cls._execution_lock(execution):
            if execution.has_destructive_changes and not confirm_destructive:
                raise TerraformExecutionError(
                    "DESTRUCTIVE_APPROVAL_REQUIRED",
                    "Destructive or replacement changes require explicit confirmation",
                )
            if cls._mark_stale_if_needed(db, execution):
                return execution
            execution.state = TerraformExecutionState.APPROVED.value
            execution.approved_by = approved_by
            execution.approved_at = datetime.now(timezone.utc)
            execution.approved_generation_hash = execution.generation_hash
            execution.approved_plan_hash = execution.plan_artifact_hash
            cls._audit(
                db,
                execution,
                TerraformExecutionEventType.APPROVAL_GRANTED.value,
                {
                    "approved_by": approved_by,
                    "destructive_confirmed": confirm_destructive,
                },
            )
            db.commit()
            db.refresh(execution)
            return execution

    @classmethod
    def reject_plan(
        cls,
        db: Session,
        execution_id: UUID,
        rejected_by: str,
        reason: Optional[str] = None,
    ) -> TerraformExecution:
        execution = cls._get_execution(db, execution_id)
        cls._require_state(
            execution, {TerraformExecutionState.AWAITING_APPROVAL.value}
        )
        with cls._execution_lock(execution):
            execution.state = TerraformExecutionState.REJECTED.value
            execution.rejected_by = rejected_by
            execution.rejected_at = datetime.now(timezone.utc)
            execution.rejection_reason = cls._redact_text(reason or "") or None
            cls._audit(
                db,
                execution,
                TerraformExecutionEventType.APPROVAL_REJECTED.value,
                {"rejected_by": rejected_by, "reason": execution.rejection_reason},
            )
            db.commit()
            db.refresh(execution)
            return execution

    @classmethod
    def apply_approved_plan(
        cls,
        db: Session,
        execution_id: UUID,
        runner: Optional[TerraformCommandRunner] = None,
        runtime_environment: Optional[Dict[str, str]] = None,
    ) -> TerraformExecution:
        execution = cls._get_execution(db, execution_id)
        cls._require_state(execution, {TerraformExecutionState.APPROVED.value})
        with cls._execution_lock(execution):
            if cls._mark_stale_if_needed(db, execution):
                return execution
            compliance_error = cls._evaluate_compliance_gate(
                db,
                execution.architecture_id,
                execution.architecture_version_id,
                execution.compliance_frameworks or [],
            )
            if compliance_error:
                return cls._mark_stale(db, execution, compliance_error)
            if (
                execution.approved_generation_hash != execution.generation_hash
                or execution.approved_plan_hash != execution.plan_artifact_hash
            ):
                return cls._mark_stale(
                    db, execution, "Approved hashes do not match the execution artifacts"
                )

            execution.state = TerraformExecutionState.APPLYING.value
            cls._audit(db, execution, TerraformExecutionEventType.APPLY_STARTED.value)
            db.commit()
            result = cls._run_command(
                runner,
                [
                    settings.terraform_binary,
                    "apply",
                    "-input=false",
                    "-no-color",
                    execution.plan_filename,
                ],
                cls._workspace(execution),
                "apply",
                runtime_environment,
                {0},
            )
            cls._save_command_result(execution, "apply", result)
            if result["status"] != "SUCCEEDED":
                return cls._fail_operation(
                    db,
                    execution,
                    "apply",
                    result,
                    TerraformExecutionEventType.APPLY_FAILED.value,
                )
            execution.state = TerraformExecutionState.SUCCEEDED.value
            cls._audit(db, execution, TerraformExecutionEventType.APPLY_COMPLETED.value)
            db.commit()
            db.refresh(execution)
            return execution

    @staticmethod
    def get_execution(db: Session, execution_id: UUID) -> Optional[TerraformExecution]:
        return (
            db.query(TerraformExecution)
            .filter(TerraformExecution.id == execution_id)
            .first()
        )

    @staticmethod
    def list_events(db: Session, execution_id: UUID) -> List[TerraformExecutionEvent]:
        return (
            db.query(TerraformExecutionEvent)
            .filter(TerraformExecutionEvent.execution_id == execution_id)
            .order_by(TerraformExecutionEvent.created_at, TerraformExecutionEvent.id)
            .all()
        )

    @classmethod
    def normalize_plan(cls, plan_document: dict) -> dict:
        """Convert Terraform plan JSON into stable application-level actions."""
        if not isinstance(plan_document, dict):
            raise ValueError("Terraform plan JSON must be an object")
        resource_changes = plan_document.get("resource_changes", [])
        if not isinstance(resource_changes, list):
            raise ValueError("Terraform plan resource_changes must be a list")
        for resource_change in resource_changes:
            if not isinstance(resource_change, dict):
                raise ValueError("Terraform resource change must be an object")
            address = resource_change.get("address")
            actions = resource_change.get("change", {}).get("actions")
            if not isinstance(address, str) or not address:
                raise ValueError("Terraform resource change is missing an address")
            if not isinstance(actions, list) or not actions:
                raise ValueError(f"Terraform resource change {address} has no actions")
        summary = {
            "add": 0,
            "change": 0,
            "destroy": 0,
            "replace": 0,
            "no_change": 0,
            "changes": [],
        }
        for resource_change in sorted(
            resource_changes,
            key=lambda item: item.get("address", ""),
        ):
            actions = list(resource_change.get("change", {}).get("actions", []))
            normalized = cls._normalize_actions(actions)
            summary[normalized.lower()] += 1
            summary["changes"].append(
                {
                    "address": resource_change.get("address", ""),
                    "action": normalized,
                    "actions": actions,
                    "destructive": normalized
                    in {
                        TerraformPlanAction.DESTROY.value,
                        TerraformPlanAction.REPLACE.value,
                    },
                }
            )
        return summary

    @staticmethod
    def _normalize_actions(actions: List[str]) -> str:
        if actions in (["delete", "create"], ["create", "delete"]):
            return TerraformPlanAction.REPLACE.value
        if actions == ["create"]:
            return TerraformPlanAction.ADD.value
        if actions == ["update"]:
            return TerraformPlanAction.CHANGE.value
        if actions == ["delete"]:
            return TerraformPlanAction.DESTROY.value
        if actions in (["no-op"], ["read"]):
            return TerraformPlanAction.NO_CHANGE.value
        raise ValueError(f"Unsupported Terraform plan actions: {actions}")

    @classmethod
    def _evaluate_compliance_gate(
        cls,
        db: Session,
        architecture_id: UUID,
        version_id: UUID,
        frameworks: List[str],
    ) -> Optional[str]:
        if not frameworks:
            return None
        result = ComplianceEngine.evaluate_compliance(
            db, architecture_id, version_id, frameworks
        )
        if result.get("error"):
            return "Compliance evaluation could not be completed"
        for evaluation in result.get("evaluations", []):
            if evaluation.get("error"):
                return "Compliance evaluation could not be completed"
            if evaluation.get("overall_status") in {
                "BLOCKED",
                "VALIDATION_BLOCKED",
            }:
                return "Technical compliance policy blocked Terraform execution"
        return None

    @classmethod
    def _mark_stale_if_needed(
        cls, db: Session, execution: TerraformExecution
    ) -> bool:
        generation = TerraformGenerator.generate(
            db, execution.architecture_id, execution.architecture_version_id
        )
        if generation["status"] != "GENERATED":
            cls._mark_stale(db, execution, "Architecture no longer generates Terraform")
            return True
        current_generation_hash = cls._generation_hash(
            generation["generator_version"], generation["files"]
        )
        if current_generation_hash != execution.generation_hash:
            cls._mark_stale(db, execution, "Generated Terraform changed after preparation")
            return True
        try:
            workspace = cls._workspace(execution)
        except TerraformExecutionError:
            cls._mark_stale(db, execution, "Terraform workspace is unavailable")
            return True
        workspace_hash = cls._workspace_generation_hash(
            workspace, execution.generator_version
        )
        if workspace_hash != execution.generation_hash:
            cls._mark_stale(db, execution, "Workspace Terraform files changed")
            return True
        if execution.plan_filename and execution.plan_artifact_hash:
            plan_path = cls._safe_child(
                workspace, execution.plan_filename
            )
            if (
                not plan_path.is_file()
                or cls._hash_file(plan_path) != execution.plan_artifact_hash
            ):
                cls._mark_stale(db, execution, "Saved plan artifact changed")
                return True
        return False

    @classmethod
    def _mark_stale(
        cls, db: Session, execution: TerraformExecution, message: str
    ) -> TerraformExecution:
        execution.state = TerraformExecutionState.STALE.value
        execution.last_error = message
        cls._audit(
            db,
            execution,
            TerraformExecutionEventType.STALE_PLAN_DETECTED.value,
            {"code": "STALE_PLAN", "message": message},
        )
        db.commit()
        db.refresh(execution)
        return execution

    @classmethod
    def _fail_operation(
        cls,
        db: Session,
        execution: TerraformExecution,
        operation: str,
        result: dict,
        event_type: str,
    ) -> TerraformExecution:
        cls._save_command_result(execution, operation, result)
        execution.state = TerraformExecutionState.FAILED.value
        execution.last_error = result.get("stderr") or f"Terraform {operation} failed"
        cls._audit(
            db,
            execution,
            event_type,
            {"operation": operation, "error_code": result.get("error_code")},
        )
        db.commit()
        db.refresh(execution)
        return execution

    @classmethod
    def _run_command(
        cls,
        runner: Optional[TerraformCommandRunner],
        arguments: List[str],
        workspace: Path,
        operation: str,
        runtime_environment: Optional[Dict[str, str]],
        accepted_exit_codes: Set[int],
    ) -> dict:
        command_runner = runner or TerraformCommandRunner()
        secret_values = [
            value
            for key, value in (runtime_environment or {}).items()
            if cls._looks_sensitive_environment_key(key)
        ]
        try:
            raw = command_runner.run(
                arguments,
                workspace,
                settings.terraform_command_timeout_seconds,
                runtime_environment,
            )
            exit_code = raw.get("exit_code")
            return {
                "operation": operation,
                "status": "SUCCEEDED" if exit_code in accepted_exit_codes else "FAILED",
                "exit_code": exit_code,
                "stdout": cls._redact_and_limit(raw.get("stdout", ""), secret_values),
                "stderr": cls._redact_and_limit(raw.get("stderr", ""), secret_values),
                "error_code": None if exit_code in accepted_exit_codes else "TERRAFORM_COMMAND_FAILED",
            }
        except FileNotFoundError:
            return {
                "operation": operation,
                "status": "FAILED",
                "exit_code": None,
                "stdout": "",
                "stderr": "Terraform executable is unavailable",
                "error_code": "TERRAFORM_UNAVAILABLE",
            }
        except subprocess.TimeoutExpired:
            return {
                "operation": operation,
                "status": "FAILED",
                "exit_code": None,
                "stdout": "",
                "stderr": "Terraform command timed out",
                "error_code": "TERRAFORM_TIMEOUT",
            }
        except OSError:
            return {
                "operation": operation,
                "status": "FAILED",
                "exit_code": None,
                "stdout": "",
                "stderr": "Terraform command could not be started",
                "error_code": "TERRAFORM_EXECUTION_FAILED",
            }

    @classmethod
    def _write_generated_files(cls, workspace: Path, files: Iterable[dict]) -> None:
        for generated_file in sorted(files, key=lambda item: item["path"]):
            target = cls._safe_child(workspace, generated_file["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix + ".tmp")
            temporary.write_text(generated_file["content"], encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(target)

    @classmethod
    def _workspace_generation_hash(cls, workspace: Path, generator_version: str) -> str:
        files = [
            {
                "path": path.relative_to(workspace).as_posix(),
                "content": path.read_text(encoding="utf-8"),
            }
            for path in sorted(workspace.rglob("*.tf"), key=lambda item: item.as_posix())
            if path.is_file()
        ]
        return cls._generation_hash(generator_version, files)

    @staticmethod
    def _generation_hash(generator_version: str, files: Iterable[dict]) -> str:
        payload = {
            "generator_version": generator_version,
            "files": [
                {"path": item["path"], "content": item["content"]}
                for item in sorted(files, key=lambda value: value["path"])
            ],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _workspace_key(
        architecture_id: UUID, version_id: UUID, execution_id: UUID
    ) -> str:
        return f"{architecture_id}/{version_id}/{execution_id}"

    @staticmethod
    def _architecture_lock_key(architecture_id: UUID, version_id: UUID) -> str:
        return f"{architecture_id}/{version_id}"

    @classmethod
    def _resolve_workspace(cls, workspace_key: str) -> Path:
        root = Path(settings.terraform_workspace_root).expanduser().resolve()
        return cls._safe_child(root, workspace_key)

    @classmethod
    def _workspace(cls, execution: TerraformExecution) -> Path:
        if not execution.workspace_key:
            raise TerraformExecutionError(
                "WORKSPACE_NOT_PREPARED", "Terraform workspace is not prepared"
            )
        workspace = cls._resolve_workspace(execution.workspace_key)
        if not workspace.is_dir():
            raise TerraformExecutionError(
                "WORKSPACE_NOT_FOUND", "Terraform workspace does not exist"
            )
        return workspace

    @staticmethod
    def _safe_child(root: Path, relative_path: str) -> Path:
        candidate = (root / relative_path).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError as error:
            raise TerraformExecutionError(
                "UNSAFE_WORKSPACE_PATH", "Path escapes the Terraform workspace"
            ) from error
        return candidate

    @classmethod
    @contextmanager
    def _execution_lock(cls, execution: TerraformExecution):
        key = cls._architecture_lock_key(
            execution.architecture_id, execution.architecture_version_id
        )
        with TerraformExecutionLockManager.acquire(key):
            yield

    @classmethod
    def _get_execution(cls, db: Session, execution_id: UUID) -> TerraformExecution:
        execution = cls.get_execution(db, execution_id)
        if execution is None:
            raise TerraformExecutionError(
                "EXECUTION_NOT_FOUND", f"Terraform execution {execution_id} not found"
            )
        return execution

    @staticmethod
    def _require_state(execution: TerraformExecution, allowed: Set[str]) -> None:
        if execution.state not in allowed:
            raise TerraformExecutionError(
                "INVALID_EXECUTION_STATE",
                f"Operation is not allowed while execution is {execution.state}",
            )

    @classmethod
    def _save_command_result(
        cls, execution: TerraformExecution, operation: str, result: dict
    ) -> None:
        command_results = dict(execution.command_results or {})
        command_results[operation] = result
        execution.command_results = command_results

    @staticmethod
    def _parse_terraform_version(stdout: str) -> Optional[str]:
        try:
            value = json.loads(stdout)
            return value.get("terraform_version")
        except (json.JSONDecodeError, AttributeError):
            return stdout.splitlines()[0].strip() if stdout.strip() else None

    @classmethod
    def _redact_text(
        cls, value: str, secret_values: Optional[Iterable[str]] = None
    ) -> str:
        redacted = value
        for secret in sorted(
            {item for item in (secret_values or []) if item},
            key=len,
            reverse=True,
        ):
            redacted = redacted.replace(secret, "[REDACTED]")
        for pattern in cls._REDACTION_PATTERNS:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        return redacted

    @classmethod
    def _redact_and_limit(
        cls, value: str, secret_values: Optional[Iterable[str]] = None
    ) -> str:
        redacted = cls._redact_text(value, secret_values)
        limit = max(settings.terraform_command_output_limit, 0)
        if len(redacted) <= limit:
            return redacted
        return redacted[:limit] + "\n[TRUNCATED]"

    @staticmethod
    def _looks_sensitive_environment_key(key: str) -> bool:
        normalized = re.sub(r"[^A-Za-z0-9]", "_", key).upper()
        return any(
            token in normalized
            for token in (
                "PASSWORD",
                "SECRET",
                "TOKEN",
                "API_KEY",
                "PRIVATE_KEY",
                "CONNECTION_STRING",
                "ARM_CLIENT_SECRET",
            )
        )

    @classmethod
    def _audit(
        cls,
        db: Session,
        execution: TerraformExecution,
        event_type: str,
        details: Optional[dict] = None,
    ) -> None:
        event = TerraformExecutionEvent(
            execution_id=execution.id,
            event_type=event_type,
            details=cls._redact_structure(details or {}),
        )
        db.add(event)

    @classmethod
    def _redact_structure(cls, value):
        if isinstance(value, dict):
            return {
                key: (
                    "[REDACTED]"
                    if cls._looks_sensitive_environment_key(str(key))
                    else cls._redact_structure(item)
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [cls._redact_structure(item) for item in value]
        if isinstance(value, str):
            return cls._redact_text(value)
        return value
