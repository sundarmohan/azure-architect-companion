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
