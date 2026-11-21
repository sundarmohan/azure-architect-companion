from fastapi import APIRouter

from app.domains.architecture.catalog import AZURE_ARCHITECTURE_PATTERNS, AZURE_CAPABILITY_MODEL, AZURE_RESOURCE_CATALOG
from app.domains.architecture.configuration import AZURE_RESOURCE_CONFIGURATION
from app.domains.architecture.schemas import AzureResourceCatalogItem

router = APIRouter()


@router.get("/resource-catalog", response_model=list[AzureResourceCatalogItem])
async def get_resource_catalog():
    return AZURE_RESOURCE_CATALOG


@router.get("/resource-capabilities")
async def get_resource_capabilities():
    return list(AZURE_CAPABILITY_MODEL.values())


@router.get("/architecture-patterns")
async def get_architecture_patterns():
    return AZURE_ARCHITECTURE_PATTERNS


@router.get("/resource-configurations")
async def get_resource_configurations():
    return list(AZURE_RESOURCE_CONFIGURATION.values())
