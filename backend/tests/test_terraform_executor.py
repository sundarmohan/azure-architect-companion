"""Tests for Milestone 7 Terraform execution lifecycle using fake runners."""

import json
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Architecture, ArchitectureVersion, Resource, ResourceCatalog
from app.services import (
    ComplianceEngine,
    TerraformCommandRunner,
    TerraformExecutionError,
    TerraformExecutionLockManager,
    TerraformExecutionService,
)


RESOURCE_GROUP = "microsoft.resources/resourcegroups"


class FakeTerraformRunner:
    """Deterministic Terraform process substitute that never contacts Azure."""

    def __init__(self, failures=None, plan_document=None, plan_exit_code=2):
        self.failures = failures or {}
        self.plan_document = plan_document or {"resource_changes": []}
        self.plan_exit_code = plan_exit_code
        self.calls = []

    def run(self, arguments, cwd, timeout_seconds, environment=None):
        self.calls.append(
            {
                "arguments": arguments,
                "cwd": cwd,
                "timeout_seconds": timeout_seconds,
                "environment": environment,
            }
        )
        operation = arguments[1]
        if operation in self.failures:
            return {
                "exit_code": 1,
                "stdout": "",
                "stderr": self.failures[operation],
            }
        if operation == "version":
            return {
                "exit_code": 0,
                "stdout": json.dumps({"terraform_version": "1.9.8"}),
                "stderr": "",
            }
        if operation == "plan":
            (cwd / TerraformExecutionService.PLAN_FILENAME).write_bytes(b"saved-plan")
            return {"exit_code": self.plan_exit_code, "stdout": "plan complete", "stderr": ""}
        if operation == "show":
            return {
                "exit_code": 0,
                "stdout": json.dumps(self.plan_document),
                "stderr": "",
            }
        return {"exit_code": 0, "stdout": f"{operation} complete", "stderr": ""}


class MissingTerraformRunner:
    def run(self, arguments, cwd, timeout_seconds, environment=None):
        raise FileNotFoundError("terraform")


class TimeoutTerraformRunner:
    def run(self, arguments, cwd, timeout_seconds, environment=None):
        raise subprocess.TimeoutExpired(arguments, timeout_seconds)


@pytest.fixture
def workspace_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "terraform_workspace_root", str(tmp_path))
    monkeypatch.setattr(settings, "terraform_command_timeout_seconds", 10)
    return tmp_path


@pytest.fixture
def execution_architecture(db: Session):
    catalog = ResourceCatalog(
        provider="azure",
        resource_type=RESOURCE_GROUP,
        display_name="Resource Group",
        category="management",
        version="1.0",
        enabled=True,
        terraform_mapping={
            "terraform_type": "azurerm_resource_group",
            "provider": "azurerm",
        },
    )
    architecture = Architecture(name="Execution Architecture", provider="azure")
    db.add_all([catalog, architecture])
    db.flush()
    version = ArchitectureVersion(
        architecture_id=architecture.id,
        version_number="1.0",
        status="draft",
    )
    db.add(version)
    db.flush()
    resource = Resource(
        architecture_version_id=version.id,
        resource_key="rg-main",
        resource_type=RESOURCE_GROUP,
        name="rg-main",
        location="eastus",
    )
    db.add(resource)
    db.commit()
    return architecture, version, resource


def prepare_execution(db, workspace_root, execution_architecture):
    architecture, version, _ = execution_architecture
    return TerraformExecutionService.prepare_workspace(
        db, architecture.id, version.id
    )


def initialize_execution(db, execution, runner=None):
    return TerraformExecutionService.initialize(
        db, execution.id, runner or FakeTerraformRunner()
    )


def validate_execution(db, execution, runner=None):
    return TerraformExecutionService.validate(
        db, execution.id, runner or FakeTerraformRunner()
    )


def plan_execution(db, execution, runner=None):
    return TerraformExecutionService.create_plan(
        db, execution.id, runner or FakeTerraformRunner()
    )


def prepared_plan(db, workspace_root, execution_architecture, plan_document=None):
    execution = prepare_execution(db, workspace_root, execution_architecture)
    runner = FakeTerraformRunner(plan_document=plan_document)
    initialize_execution(db, execution, runner)
    validate_execution(db, execution, runner)
    plan_execution(db, execution, runner)
    return execution, runner


class TestWorkspacePreparation:
    def test_workspace_creation(self, db, workspace_root, execution_architecture):
        execution = prepare_execution(db, workspace_root, execution_architecture)

        workspace = TerraformExecutionService._workspace(execution)
        assert execution.state == "GENERATED"
        assert (workspace / "resource_group.tf").is_file()
        assert (workspace / "provider.tf").is_file()
        assert execution.generation_hash

    def test_workspace_path_safety(self, workspace_root):
        with pytest.raises(TerraformExecutionError) as error:
            TerraformExecutionService._safe_child(workspace_root, "../escape.tf")

        assert error.value.code == "UNSAFE_WORKSPACE_PATH"

    def test_validation_error_blocks_workspace(self, db, workspace_root, execution_architecture):
        architecture, version, resource = execution_architecture
        resource.resource_type = "unknown/provider"
        db.commit()

        execution = TerraformExecutionService.prepare_workspace(
            db, architecture.id, version.id
        )

        assert execution.state == "FAILED"
        assert execution.workspace_key is None
        assert execution.last_error == "Terraform generation was blocked"

    def test_compliance_blocked_stops_preparation(
        self, db, workspace_root, execution_architecture, monkeypatch
    ):
        architecture, version, _ = execution_architecture
        monkeypatch.setattr(
            ComplianceEngine,
            "evaluate_compliance",
            staticmethod(
                lambda *args: {
                    "evaluations": [{"overall_status": "BLOCKED"}]
                }
            ),
        )

        execution = TerraformExecutionService.prepare_workspace(
            db, architecture.id, version.id, ["HIPAA"]
        )

        assert execution.state == "FAILED"
        assert execution.last_error == "Technical compliance policy blocked Terraform execution"


class TestInitializationAndValidation:
    def test_terraform_unavailable(self, db, workspace_root, execution_architecture):
        execution = prepare_execution(db, workspace_root, execution_architecture)

        result = initialize_execution(db, execution, MissingTerraformRunner())

        assert result.state == "FAILED"
        assert result.command_results["version"]["error_code"] == "TERRAFORM_UNAVAILABLE"

    def test_init_success(self, db, workspace_root, execution_architecture):
        execution = prepare_execution(db, workspace_root, execution_architecture)
        runner = FakeTerraformRunner()

        result = initialize_execution(db, execution, runner)

        assert result.state == "INITIALIZED"
        assert result.terraform_version == "1.9.8"
        assert runner.calls[1]["arguments"] == [
            settings.terraform_binary,
            "init",
            "-input=false",
            "-no-color",
        ]

    def test_init_failure(self, db, workspace_root, execution_architecture):
        execution = prepare_execution(db, workspace_root, execution_architecture)

        result = initialize_execution(
            db, execution, FakeTerraformRunner(failures={"init": "init failed"})
        )

        assert result.state == "FAILED"
        assert result.command_results["init"]["exit_code"] == 1

    def test_validate_success(self, db, workspace_root, execution_architecture):
        execution = prepare_execution(db, workspace_root, execution_architecture)
        initialize_execution(db, execution)

        result = validate_execution(db, execution)

        assert result.state == "VALIDATED"
        assert result.command_results["validate"]["status"] == "SUCCEEDED"

    def test_validate_failure_stops_lifecycle(self, db, workspace_root, execution_architecture):
        execution = prepare_execution(db, workspace_root, execution_architecture)
        initialize_execution(db, execution)

        result = validate_execution(
            db, execution, FakeTerraformRunner(failures={"validate": "invalid HCL"})
        )

        assert result.state == "FAILED"
        assert "invalid HCL" in result.last_error

    def test_command_timeout(self, db, workspace_root, execution_architecture):
        execution = prepare_execution(db, workspace_root, execution_architecture)

        result = initialize_execution(db, execution, TimeoutTerraformRunner())

        assert result.state == "FAILED"
        assert result.command_results["version"]["error_code"] == "TERRAFORM_TIMEOUT"


class TestPlanning:
    def test_plan_success_creates_saved_artifact(self, db, workspace_root, execution_architecture):
        execution = prepare_execution(db, workspace_root, execution_architecture)
        runner = FakeTerraformRunner()
        initialize_execution(db, execution, runner)
        validate_execution(db, execution, runner)

        result = plan_execution(db, execution, runner)

        assert result.state == "AWAITING_APPROVAL"
        assert result.plan_artifact_hash
        plan_call = next(call for call in runner.calls if call["arguments"][1] == "plan")
        assert "-out=execution.tfplan" in plan_call["arguments"]
        assert "-detailed-exitcode" in plan_call["arguments"]

    def test_plan_failure(self, db, workspace_root, execution_architecture):
        execution = prepare_execution(db, workspace_root, execution_architecture)
        initialize_execution(db, execution)
        validate_execution(db, execution)

        result = plan_execution(
            db, execution, FakeTerraformRunner(failures={"plan": "plan failed"})
        )

        assert result.state == "FAILED"
        assert result.command_results["plan"]["status"] == "FAILED"

    def test_plan_change_parsing(self):
        summary = TerraformExecutionService.normalize_plan(
            {
                "resource_changes": [
                    {"address": "azurerm_resource_group.new", "change": {"actions": ["create"]}},
                    {"address": "azurerm_subnet.app", "change": {"actions": ["update"]}},
                    {"address": "azurerm_storage_account.old", "change": {"actions": ["delete"]}},
                    {"address": "azurerm_network_interface.nic", "change": {"actions": ["delete", "create"]}},
                    {"address": "azurerm_virtual_network.vnet", "change": {"actions": ["no-op"]}},
                ]
            }
        )

        assert summary["add"] == 1
        assert summary["change"] == 1
        assert summary["destroy"] == 1
        assert summary["replace"] == 1
        assert summary["no_change"] == 1
        assert [item["address"] for item in summary["changes"]] == sorted(
            item["address"] for item in summary["changes"]
        )

    @pytest.mark.parametrize(
        "resource_change",
        [
            {"change": {"actions": ["create"]}},
            {"address": "azurerm_resource_group.missing", "change": {}},
            {
                "address": "azurerm_resource_group.unknown",
                "change": {"actions": ["future-action"]},
            },
        ],
    )
    def test_plan_change_parsing_rejects_malformed_actions(self, resource_change):
        with pytest.raises(ValueError):
            TerraformExecutionService.normalize_plan(
                {"resource_changes": [resource_change]}
            )

    def test_plan_json_is_not_persisted(self, db, workspace_root, execution_architecture):
        plan_document = {
            "resource_changes": [],
            "variables": {"administrator_password": {"value": "never-store-me"}},
        }
        execution, _ = prepared_plan(
            db, workspace_root, execution_architecture, plan_document
        )

        assert "never-store-me" not in str(execution.command_results)
        assert execution.command_results["show"]["stdout"] == (
            "Terraform plan JSON normalized into plan_summary"
        )


class TestApprovalAndApply:
    def test_approval(self, db, workspace_root, execution_architecture):
        execution, _ = prepared_plan(db, workspace_root, execution_architecture)

        result = TerraformExecutionService.approve_plan(
            db, execution.id, "architect@example.test"
        )

        assert result.state == "APPROVED"
        assert result.approved_generation_hash == result.generation_hash
        assert result.approved_plan_hash == result.plan_artifact_hash

    def test_rejection(self, db, workspace_root, execution_architecture):
        execution, _ = prepared_plan(db, workspace_root, execution_architecture)

        result = TerraformExecutionService.reject_plan(
            db, execution.id, "architect@example.test", "Requires revision"
        )

        assert result.state == "REJECTED"
        assert result.rejection_reason == "Requires revision"

    def test_stale_generation_rejected(self, db, workspace_root, execution_architecture):
        execution, _ = prepared_plan(db, workspace_root, execution_architecture)
        _, _, resource = execution_architecture
        resource.location = "westus"
        db.commit()

        result = TerraformExecutionService.approve_plan(
            db, execution.id, "architect@example.test"
        )

        assert result.state == "STALE"
        assert "changed" in result.last_error.lower()

    def test_stale_plan_artifact_rejected(self, db, workspace_root, execution_architecture):
        execution, _ = prepared_plan(db, workspace_root, execution_architecture)
        TerraformExecutionService.approve_plan(
            db, execution.id, "architect@example.test"
        )
        plan_path = TerraformExecutionService._workspace(execution) / execution.plan_filename
        plan_path.write_bytes(b"tampered-plan")

        result = TerraformExecutionService.apply_approved_plan(
            db, execution.id, FakeTerraformRunner()
        )

        assert result.state == "STALE"
        assert "artifact changed" in result.last_error.lower()

    def test_missing_workspace_marks_approved_plan_stale(
        self, db, workspace_root, execution_architecture
    ):
        execution, _ = prepared_plan(db, workspace_root, execution_architecture)
        TerraformExecutionService.approve_plan(
            db, execution.id, "architect@example.test"
        )
        shutil.rmtree(TerraformExecutionService._workspace(execution))

        result = TerraformExecutionService.apply_approved_plan(
            db, execution.id, FakeTerraformRunner()
        )

        assert result.state == "STALE"
        assert result.last_error == "Terraform workspace is unavailable"

    def test_apply_success_uses_saved_plan(self, db, workspace_root, execution_architecture):
        execution, runner = prepared_plan(db, workspace_root, execution_architecture)
        TerraformExecutionService.approve_plan(
            db, execution.id, "architect@example.test"
        )

        result = TerraformExecutionService.apply_approved_plan(
            db, execution.id, runner
        )

        assert result.state == "SUCCEEDED"
        apply_call = runner.calls[-1]
        assert apply_call["arguments"] == [
            settings.terraform_binary,
            "apply",
            "-input=false",
            "-no-color",
            "execution.tfplan",
        ]

    def test_apply_failure(self, db, workspace_root, execution_architecture):
        execution, _ = prepared_plan(db, workspace_root, execution_architecture)
        TerraformExecutionService.approve_plan(
            db, execution.id, "architect@example.test"
        )

        result = TerraformExecutionService.apply_approved_plan(
            db, execution.id, FakeTerraformRunner(failures={"apply": "apply failed"})
        )

        assert result.state == "FAILED"
        assert result.command_results["apply"]["status"] == "FAILED"

    def test_apply_before_approval_is_rejected(self, db, workspace_root, execution_architecture):
        execution = prepare_execution(db, workspace_root, execution_architecture)

        with pytest.raises(TerraformExecutionError) as error:
            TerraformExecutionService.apply_approved_plan(
                db, execution.id, FakeTerraformRunner()
            )

        assert error.value.code == "INVALID_EXECUTION_STATE"


class TestDestructivePlans:
    @pytest.fixture
    def destructive_plan(self):
        return {
            "resource_changes": [
                {
                    "address": "azurerm_storage_account.old",
                    "change": {"actions": ["delete"]},
                }
            ]
        }

    def test_destructive_change_detection(
        self, db, workspace_root, execution_architecture, destructive_plan
    ):
        execution, _ = prepared_plan(
            db, workspace_root, execution_architecture, destructive_plan
        )

        assert execution.has_destructive_changes is True
        assert execution.plan_summary["changes"][0]["destructive"] is True

    def test_destructive_plan_requires_confirmation(
        self, db, workspace_root, execution_architecture, destructive_plan
    ):
        execution, _ = prepared_plan(
            db, workspace_root, execution_architecture, destructive_plan
        )

        with pytest.raises(TerraformExecutionError) as error:
            TerraformExecutionService.approve_plan(
                db, execution.id, "architect@example.test"
            )

        assert error.value.code == "DESTRUCTIVE_APPROVAL_REQUIRED"

    def test_destructive_plan_can_be_explicitly_approved(
        self, db, workspace_root, execution_architecture, destructive_plan
    ):
        execution, _ = prepared_plan(
            db, workspace_root, execution_architecture, destructive_plan
        )

        result = TerraformExecutionService.approve_plan(
            db,
            execution.id,
            "architect@example.test",
            confirm_destructive=True,
        )

        assert result.state == "APPROVED"


class TestSecurityConcurrencyAndAudit:
    def test_concurrent_operation_is_blocked(self, db, workspace_root, execution_architecture):
        execution = prepare_execution(db, workspace_root, execution_architecture)
        key = TerraformExecutionService._architecture_lock_key(
            execution.architecture_id, execution.architecture_version_id
        )

        with TerraformExecutionLockManager.acquire(key):
            with pytest.raises(TerraformExecutionError) as error:
                initialize_execution(db, execution)

        assert error.value.code == "EXECUTION_LOCKED"

    def test_command_output_and_environment_secrets_are_redacted(
        self, workspace_root
    ):
        class SecretRunner:
            def run(self, arguments, cwd, timeout_seconds, environment=None):
                return {
                    "exit_code": 0,
                    "stdout": "ARM_CLIENT_SECRET=super-secret-value",
                    "stderr": "token: bearer-token-value",
                }

        result = TerraformExecutionService._run_command(
            SecretRunner(),
            ["terraform", "version", "-json"],
            workspace_root,
            "version",
            {"ARM_CLIENT_SECRET": "super-secret-value"},
            {0},
        )

        assert "super-secret-value" not in str(result)
        assert "bearer-token-value" not in str(result)
        assert "[REDACTED]" in str(result)

    def test_command_output_is_truncated_after_redaction(
        self, workspace_root, monkeypatch
    ):
        class LargeOutputRunner:
            def run(self, arguments, cwd, timeout_seconds, environment=None):
                return {"exit_code": 0, "stdout": "password=hidden\n" + "x" * 20, "stderr": ""}

        monkeypatch.setattr(settings, "terraform_command_output_limit", 10)
        result = TerraformExecutionService._run_command(
            LargeOutputRunner(),
            ["terraform", "version", "-json"],
            workspace_root,
            "version",
            None,
            {0},
        )

        assert "hidden" not in result["stdout"]
        assert result["stdout"].endswith("[TRUNCATED]")

    def test_command_runner_uses_argument_array_without_shell(self, tmp_path, monkeypatch):
        captured = {}

        def fake_run(arguments, **kwargs):
            captured["arguments"] = arguments
            captured.update(kwargs)
            return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        monkeypatch.setattr(subprocess, "run", fake_run)
        TerraformCommandRunner().run(["terraform", "version", "-json"], tmp_path, 10)

        assert captured["arguments"] == ["terraform", "version", "-json"]
        assert captured["shell"] is False
        assert captured["stdin"] is subprocess.DEVNULL

    def test_audit_events_record_lifecycle(self, db, workspace_root, execution_architecture):
        execution, _ = prepared_plan(db, workspace_root, execution_architecture)
        TerraformExecutionService.approve_plan(
            db, execution.id, "architect@example.test"
        )
        events = TerraformExecutionService.list_events(db, execution.id)

        event_types = [event.event_type for event in events]
        assert "WORKSPACE_PREPARED" in event_types
        assert "INIT_COMPLETED" in event_types
        assert "VALIDATION_COMPLETED" in event_types
        assert "PLAN_COMPLETED" in event_types
        assert "APPROVAL_GRANTED" in event_types


class TestTerraformExecutionAPI:
    def test_prepare_and_get_execution(
        self, client, db, workspace_root, execution_architecture
    ):
        architecture, version, _ = execution_architecture

        prepare_response = client.post(
            f"/architectures/{architecture.id}/versions/{version.id}/terraform/executions",
            json={"compliance_frameworks": []},
        )

        assert prepare_response.status_code == 201
        execution_id = prepare_response.json()["id"]
        get_response = client.get(f"/terraform/executions/{execution_id}")
        assert get_response.status_code == 200
        assert get_response.json()["state"] == "GENERATED"

    def test_invalid_transition_returns_conflict(
        self, client, db, workspace_root, execution_architecture
    ):
        architecture, version, _ = execution_architecture
        response = client.post(
            f"/architectures/{architecture.id}/versions/{version.id}/terraform/executions",
            json={"compliance_frameworks": []},
        )
        execution_id = response.json()["id"]

        apply_response = client.post(f"/terraform/executions/{execution_id}/apply")

        assert apply_response.status_code == 409
        assert apply_response.json()["detail"]["code"] == "INVALID_EXECUTION_STATE"

    def test_missing_execution_returns_not_found(self, client):
        response = client.get(f"/terraform/executions/{uuid4()}")

        assert response.status_code == 404
