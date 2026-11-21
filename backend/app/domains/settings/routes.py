from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from .schemas import (
    AzureCredentialsWrite,
    AzureIntegrationStatusRead,
    AzureSubscriptionInventoryRead,
    CloudAccountCredentialsWrite,
    CloudAccountStatusRead,
    ProviderConfigWrite,
    ProviderConnectionTestRead,
    ProviderStatusRead,
    SettingsOverviewRead,
)
from .service import SettingsService

router = APIRouter()


async def get_db():
    async with SessionLocal() as session:
        yield session


def _normalize_provider(provider_name: str) -> str:
    return str(provider_name or "").strip().lower()


def _get_service() -> SettingsService:
    return SettingsService()


def _require_provider_or_404(service: SettingsService, provider: str) -> None:
    if not service.is_supported_provider(provider):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not supported")


def _require_cloud_provider_or_404(service: SettingsService, provider: str) -> None:
    if not service.is_supported_cloud_provider(provider):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cloud provider not supported")


@router.get("", response_model=SettingsOverviewRead)
async def get_settings_overview(db: AsyncSession = Depends(get_db)):
    service = _get_service()
    return await service.get_settings_overview(db=db)


@router.put("/providers/{provider_name}", response_model=ProviderStatusRead)
async def update_provider_key(provider_name: str, payload: ProviderConfigWrite, db: AsyncSession = Depends(get_db)):
    service = _get_service()
    provider = _normalize_provider(provider_name)
    _require_provider_or_404(service, provider)
    return await service.save_provider_key(provider=provider, api_key=payload.api_key, db=db)


@router.delete("/providers/{provider_name}", response_model=ProviderStatusRead)
async def clear_provider_key(provider_name: str, db: AsyncSession = Depends(get_db)):
    service = _get_service()
    provider = _normalize_provider(provider_name)
    _require_provider_or_404(service, provider)
    return await service.clear_provider_key(provider=provider, db=db)


@router.post("/providers/{provider_name}/test", response_model=ProviderConnectionTestRead)
async def test_provider_connection(provider_name: str, db: AsyncSession = Depends(get_db)):
    service = _get_service()
    provider = _normalize_provider(provider_name)
    _require_provider_or_404(service, provider)
    return await service.test_provider_connection(provider=provider, db=db)


@router.get("/azure/status", response_model=AzureIntegrationStatusRead)
async def get_azure_status(db: AsyncSession = Depends(get_db)):
    service = _get_service()
    return await service.get_azure_status(db=db)


@router.put("/azure/credentials", response_model=AzureIntegrationStatusRead)
async def save_azure_credentials(payload: AzureCredentialsWrite, db: AsyncSession = Depends(get_db)):
    service = _get_service()
    return await service.save_azure_credentials(payload=payload, db=db)


@router.delete("/azure/credentials", response_model=AzureIntegrationStatusRead)
async def clear_azure_credentials(db: AsyncSession = Depends(get_db)):
    service = _get_service()
    return await service.clear_azure_credentials(db=db)


@router.post("/azure/test", response_model=AzureIntegrationStatusRead)
async def test_azure_status(db: AsyncSession = Depends(get_db)):
    service = _get_service()
    return await service.test_azure_connection(db=db)


@router.get("/azure/subscriptions", response_model=list[AzureSubscriptionInventoryRead])
async def list_azure_subscriptions(db: AsyncSession = Depends(get_db)):
    service = _get_service()
    return await service.list_azure_subscription_inventory(db=db)


@router.get("/cloud-accounts", response_model=list[CloudAccountStatusRead])
async def list_cloud_accounts(db: AsyncSession = Depends(get_db)):
    service = _get_service()
    return await service.get_cloud_accounts(db=db)


@router.get("/cloud-accounts/{provider_name}/status", response_model=CloudAccountStatusRead)
async def get_cloud_account_status(provider_name: str, db: AsyncSession = Depends(get_db)):
    service = _get_service()
    provider = _normalize_provider(provider_name)
    _require_cloud_provider_or_404(service, provider)
    return await service.get_cloud_account_status(provider=provider, db=db)


@router.put("/cloud-accounts/{provider_name}/credentials", response_model=CloudAccountStatusRead)
async def save_cloud_account_credentials(
    provider_name: str,
    payload: CloudAccountCredentialsWrite,
    db: AsyncSession = Depends(get_db),
):
    service = _get_service()
    provider = _normalize_provider(provider_name)
    _require_cloud_provider_or_404(service, provider)
    if provider == "azure":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use /api/settings/azure/credentials for Azure credentials.",
        )
    return await service.save_cloud_account_credentials(provider=provider, payload=payload, db=db)


@router.delete("/cloud-accounts/{provider_name}/credentials", response_model=CloudAccountStatusRead)
async def clear_cloud_account_credentials(provider_name: str, db: AsyncSession = Depends(get_db)):
    service = _get_service()
    provider = _normalize_provider(provider_name)
    _require_cloud_provider_or_404(service, provider)
    if provider == "azure":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use /api/settings/azure/credentials for Azure credentials.",
        )
    return await service.clear_cloud_account_credentials(provider=provider, db=db)


@router.post("/cloud-accounts/{provider_name}/test", response_model=CloudAccountStatusRead)
async def test_cloud_account_connection(provider_name: str, db: AsyncSession = Depends(get_db)):
    service = _get_service()
    provider = _normalize_provider(provider_name)
    _require_cloud_provider_or_404(service, provider)
    return await service.test_cloud_account_connection(provider=provider, db=db)