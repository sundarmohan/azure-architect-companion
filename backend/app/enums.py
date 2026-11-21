"""
Enumerations for the application.
"""

from enum import Enum


class DependencyClassification(str, Enum):
    """Classification of dependencies as defined in Resource Catalog."""
    
    REQUIRED = "REQUIRED"
    RECOMMENDED = "RECOMMENDED"
    OPTIONAL = "OPTIONAL"


class DependencyStatus(str, Enum):
    """Status of a dependency finding - whether it's satisfied in the architecture."""
    
    SATISFIED = "SATISFIED"
    MISSING = "MISSING"


# ==================== VALIDATION ENGINE ENUMS ====================


class ValidationFindingSeverity(str, Enum):
    """Severity level of validation findings."""
    
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class ValidationCategory(str, Enum):
    """Categories of validation checks."""
    
    RESOURCE = "RESOURCE"
    HIERARCHY = "HIERARCHY"
    DEPENDENCY = "DEPENDENCY"
    RELATIONSHIP = "RELATIONSHIP"
    CATALOG = "CATALOG"


class ValidationOverallStatus(str, Enum):
    """Overall validation result status."""
    
    VALID = "VALID"
    INVALID = "INVALID"


# ==================== VALIDATION CODES ====================

class ValidationCode(str, Enum):
    """Machine-readable validation codes."""
    
    # Resource validation codes
    RESOURCE_TYPE_NOT_IN_CATALOG = "RESOURCE_TYPE_NOT_IN_CATALOG"
    DUPLICATE_RESOURCE_KEY = "DUPLICATE_RESOURCE_KEY"
    RESOURCE_MISSING_REQUIRED_IDENTITY = "RESOURCE_MISSING_REQUIRED_IDENTITY"
    INVALID_RESOURCE_TYPE = "INVALID_RESOURCE_TYPE"
    RESOURCE_MISSING_NAME = "RESOURCE_MISSING_NAME"
    
    # Hierarchy validation codes
    INVALID_PARENT_TYPE = "INVALID_PARENT_TYPE"
    INVALID_HIERARCHY_PARENT = "INVALID_HIERARCHY_PARENT"
    
    # Relationship validation codes
    INVALID_RELATIONSHIP_SOURCE = "INVALID_RELATIONSHIP_SOURCE"
    INVALID_RELATIONSHIP_TARGET = "INVALID_RELATIONSHIP_TARGET"
    SELF_REFERENCING_RELATIONSHIP = "SELF_REFERENCING_RELATIONSHIP"
    INVALID_RELATIONSHIP_TYPE = "INVALID_RELATIONSHIP_TYPE"
    
    # Dependency validation codes
    REQUIRED_DEPENDENCY_MISSING = "REQUIRED_DEPENDENCY_MISSING"
    RECOMMENDED_DEPENDENCY_MISSING = "RECOMMENDED_DEPENDENCY_MISSING"
    OPTIONAL_DEPENDENCY_MISSING = "OPTIONAL_DEPENDENCY_MISSING"
    UNKNOWN_DEPENDENCY_RESOURCE_TYPE = "UNKNOWN_DEPENDENCY_RESOURCE_TYPE"
    
    # Catalog validation codes
    CATALOG_RESOURCE_TYPE_UNKNOWN = "CATALOG_RESOURCE_TYPE_UNKNOWN"


# ==================== COMPLIANCE ENGINE ENUMS ====================


class ComplianceOutcome(str, Enum):
    """Outcome of a compliance control evaluation."""
    
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    RECOMMENDATION = "RECOMMENDATION"
    NOT_EVALUATED = "NOT_EVALUATED"


class CompliancePolicyLevel(str, Enum):
    """Policy level for compliance controls."""
    
    BLOCK = "BLOCK"
    REQUIRED = "REQUIRED"
    RECOMMENDATION = "RECOMMENDATION"


class ComplianceFrameworkName(str, Enum):
    """Supported compliance frameworks."""
    
    HIPAA = "HIPAA"
    GDPR = "GDPR"
    SOC2 = "SOC2"
    ISO27001 = "ISO27001"
    NIST = "NIST"
    HITRUST = "HITRUST"


class ComplianceControlCategory(str, Enum):
    """Categories for compliance controls."""
    
    ACCESS_CONTROL = "ACCESS_CONTROL"
    NETWORK_SECURITY = "NETWORK_SECURITY"
    DATA_PROTECTION = "DATA_PROTECTION"
    ENCRYPTION = "ENCRYPTION"
    LOGGING = "LOGGING"
    MONITORING = "MONITORING"
    BACKUP = "BACKUP"
    IDENTITY = "IDENTITY"
    SECRETS = "SECRETS"
    AVAILABILITY = "AVAILABILITY"
    INCIDENT_RESPONSE = "INCIDENT_RESPONSE"
    CONFIGURATION = "CONFIGURATION"


class ComplianceEvaluationType(str, Enum):
    """Type of compliance control evaluation."""
    
    PROPERTY_CHECK = "PROPERTY_CHECK"
    DEPENDENCY_CHECK = "DEPENDENCY_CHECK"
    RESOURCE_TYPE_CHECK = "RESOURCE_TYPE_CHECK"
    RELATIONSHIP_CHECK = "RELATIONSHIP_CHECK"


class ComplianceOverallStatus(str, Enum):
    """Overall compliance evaluation status."""
    
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    REVIEW = "REVIEW"
    PASSED = "PASSED"
    VALIDATION_BLOCKED = "VALIDATION_BLOCKED"


# ==================== TERRAFORM GENERATOR ENUMS ====================


class TerraformGenerationStatus(str, Enum):
    """Outcome of deterministic Terraform generation."""

    GENERATED = "GENERATED"
    BLOCKED = "BLOCKED"
    PARTIAL = "PARTIAL"


class TerraformGenerationCode(str, Enum):
    """Machine-readable Terraform generation finding codes."""

    INVALID_ARCHITECTURE = "INVALID_ARCHITECTURE"
    TERRAFORM_MAPPING_MISSING = "TERRAFORM_MAPPING_MISSING"
    TERRAFORM_MAPPING_INVALID = "TERRAFORM_MAPPING_INVALID"
    UNSUPPORTED_TERRAFORM_GENERATION = "UNSUPPORTED_TERRAFORM_GENERATION"
    REQUIRED_PROPERTY_MISSING = "REQUIRED_PROPERTY_MISSING"
    SECRET_CONFIGURATION_REQUIRED = "SECRET_CONFIGURATION_REQUIRED"
    GENERIC_PROPERTY_RENDERING = "GENERIC_PROPERTY_RENDERING"
    GENERATION_FAILURE = "GENERATION_FAILURE"


# ==================== TERRAFORM EXECUTION ENUMS ====================


class TerraformExecutionState(str, Enum):
    """States in the controlled Terraform plan/apply lifecycle."""

    PREPARING = "PREPARING"
    GENERATED = "GENERATED"
    INITIALIZING = "INITIALIZING"
    INITIALIZED = "INITIALIZED"
    VALIDATING = "VALIDATING"
    VALIDATED = "VALIDATED"
    PLANNING = "PLANNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    APPLYING = "APPLYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    STALE = "STALE"
    CANCELLED = "CANCELLED"


class TerraformPlanAction(str, Enum):
    """Normalized Terraform plan action."""

    ADD = "ADD"
    CHANGE = "CHANGE"
    DESTROY = "DESTROY"
    REPLACE = "REPLACE"
    NO_CHANGE = "NO_CHANGE"


class TerraformExecutionEventType(str, Enum):
    """Auditable M7 lifecycle events."""

    WORKSPACE_PREPARED = "WORKSPACE_PREPARED"
    PREPARATION_FAILED = "PREPARATION_FAILED"
    INIT_STARTED = "INIT_STARTED"
    INIT_COMPLETED = "INIT_COMPLETED"
    INIT_FAILED = "INIT_FAILED"
    VALIDATION_STARTED = "VALIDATION_STARTED"
    VALIDATION_COMPLETED = "VALIDATION_COMPLETED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    PLAN_STARTED = "PLAN_STARTED"
    PLAN_COMPLETED = "PLAN_COMPLETED"
    PLAN_FAILED = "PLAN_FAILED"
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    APPLY_STARTED = "APPLY_STARTED"
    APPLY_COMPLETED = "APPLY_COMPLETED"
    APPLY_FAILED = "APPLY_FAILED"
    APPLY_BLOCKED = "APPLY_BLOCKED"
    STALE_PLAN_DETECTED = "STALE_PLAN_DETECTED"


# ==================== ARCHITECTURE VERSIONING ENUMS ====================


class ArchitectureVersionStatus(str, Enum):
    """Lifecycle states for canonical architecture snapshots."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


class ArchitectureVersionEventType(str, Enum):
    """Append-only architecture version audit event types."""

    VERSION_CREATED = "VERSION_CREATED"
    VERSION_ACTIVATED = "VERSION_ACTIVATED"
    VERSION_REVERTED = "VERSION_REVERTED"
    VERSION_COMPARED = "VERSION_COMPARED"
    VERSION_CREATION_FAILED = "VERSION_CREATION_FAILED"


# ==================== AZURE RESOURCE INTELLIGENCE ENUMS ====================


class AzureConnectionStatus(str, Enum):
    """Normalized status for the configured read-only Azure connection."""

    CONNECTED = "CONNECTED"
    UNAVAILABLE = "UNAVAILABLE"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"
    TIMEOUT = "TIMEOUT"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"


class AzureAvailabilityStatus(str, Enum):
    """Deterministic support result; UNKNOWN must never imply support."""

    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"


class AzureProviderRegistrationStatus(str, Enum):
    REGISTERED = "REGISTERED"
    NOT_REGISTERED = "NOT_REGISTERED"
    UNKNOWN = "UNKNOWN"


class AzureQuotaStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    INSUFFICIENT = "INSUFFICIENT"
    UNKNOWN = "UNKNOWN"


class AzureFreshnessStatus(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"


class AzurePreflightStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


# ==================== CONFORMANCE AND DRIFT ENUMS ====================


class ConformanceOverallStatus(str, Enum):
    CONFORMANT = "CONFORMANT"
    DRIFTED = "DRIFTED"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"
    ERROR = "ERROR"


class ResourceConformanceStatus(str, Enum):
    CONFORMANT = "CONFORMANT"
    MODIFIED = "MODIFIED"
    MISSING = "MISSING"
    UNEXPECTED = "UNEXPECTED"
    UNKNOWN = "UNKNOWN"


class DriftCategory(str, Enum):
    CONFIGURATION = "CONFIGURATION_DRIFT"
    RESOURCE = "RESOURCE_DRIFT"
    HIERARCHY = "HIERARCHY_DRIFT"
    RELATIONSHIP = "RELATIONSHIP_DRIFT"
    DEPENDENCY = "DEPENDENCY_DRIFT"
    TAG = "TAG_DRIFT"
    LOCATION = "LOCATION_DRIFT"
    SKU = "SKU_DRIFT"
    SECURITY = "SECURITY_DRIFT"
    NETWORK = "NETWORK_DRIFT"
    MONITORING = "MONITORING_DRIFT"
    BACKUP = "BACKUP_DRIFT"


class ConformanceEventType(str, Enum):
    CONFORMANCE_STARTED = "CONFORMANCE_STARTED"
    CONFORMANCE_COMPLETED = "CONFORMANCE_COMPLETED"
    CONFORMANCE_FAILED = "CONFORMANCE_FAILED"
    DRIFT_DETECTED = "DRIFT_DETECTED"
    DRIFT_RESOLVED = "DRIFT_RESOLVED"
