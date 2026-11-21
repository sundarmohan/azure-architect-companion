from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class CostEstimateRequest(BaseModel):
    region: str | None = None


class CostEstimateItem(BaseModel):
    resource_id: str
    name: str
    resource_type: str
    region: str
    resource_group_id: str | None = None
    resource_group_name: str | None = None
    subscription_id: str | None = None
    sku: str | None = None
    quantity: float = 1.0
    meter_name: str | None = None
    unit_of_measure: str | None = None
    monthly_cost: float = 0.0
    annual_cost: float = 0.0
    currency: str = "USD"
    pricing_source: str
    warning: str | None = None
    error: str | None = None


class CostBreakdown(BaseModel):
    by_resource_type: dict[str, float] = Field(default_factory=dict)
    by_resource_group: dict[str, float] = Field(default_factory=dict)
    by_subscription: dict[str, float] = Field(default_factory=dict)


class ArchitectureCostEstimateRead(BaseModel):
    architecture_id: str
    estimation_type: str = "estimated_planned"
    pricing_source: str
    total_monthly_cost: float
    total_annual_cost: float
    currency: str
    items: list[CostEstimateItem]
    breakdown: CostBreakdown = Field(default_factory=CostBreakdown)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ActualCostRequest(BaseModel):
    subscription_id: str | None = None
    start_date: date | None = None
    end_date: date | None = None


class ActualCostDailyItem(BaseModel):
    usage_date: str
    cost: float


class ArchitectureActualCostRead(BaseModel):
    architecture_id: str
    cost_type: str = "actual_billed"
    pricing_source: str = "azure_cost_management"
    available: bool
    subscription_id: str | None = None
    currency: str = "USD"
    total_cost: float = 0.0
    start_date: str | None = None
    end_date: str | None = None
    daily: list[ActualCostDailyItem] = Field(default_factory=list)
    error: str | None = None
