"""
Core configuration for the application.
"""

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/azure_architect"
    
    # Application
    app_name: str = "Azure Architect Companion"
    debug: bool = False

    # Terraform execution
    terraform_binary: str = "terraform"
    terraform_workspace_root: str = "./terraform_workspaces"
    terraform_command_timeout_seconds: int = 600
    terraform_command_output_limit: int = 100000

    # Read-only Azure Resource Intelligence. Credentials remain environment-only.
    azure_tenant_id: str | None = None
    azure_subscription_id: str | None = None
    azure_client_id: str | None = None
    azure_client_secret: SecretStr | None = None
    azure_credential_mode: str = "default"
    azure_intelligence_cache_ttl_seconds: int = 3600
    azure_intelligence_timeout_seconds: int = 30
    azure_intelligence_max_retries: int = 2

    class Config:
        """Pydantic config."""
        env_file = ".env"
        case_sensitive = False


settings = Settings()
