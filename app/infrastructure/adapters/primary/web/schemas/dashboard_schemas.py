from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.dashboard import DashboardWindow
from app.infrastructure.adapters.primary.web.schemas.financial_schemas import FinancialAmount


class ExecutiveDashboardQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year: int = Field(ge=1, le=9998)
    month: int = Field(ge=1, le=12)
    compare_months: int = Field(
        default=3, ge=1, le=12, description="Meses previos al seleccionado."
    )

    @model_validator(mode="after")
    def validate_window(self) -> "ExecutiveDashboardQuery":
        try:
            DashboardWindow.create(self.year, self.month, self.compare_months)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
        return self


class DashboardResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MonthlyProfitResponse(DashboardResponseModel):
    period: str
    net_profit: FinancialAmount


class ProfitComparisonResponse(DashboardResponseModel):
    previous_period: str
    current_net_profit: FinancialAmount
    previous_net_profit: FinancialAmount
    absolute_change: FinancialAmount
    percentage_change: FinancialAmount | None


class PackageMetricResponse(DashboardResponseModel):
    package_id: UUID
    name: str
    events: int


class ThemeMetricResponse(DashboardResponseModel):
    theme_id: UUID | None
    name: str
    events: int


class ExtraRankingResponse(DashboardResponseModel):
    extra_id: UUID
    name: str
    times_hired: int


class DistrictMetricResponse(DashboardResponseModel):
    district: str
    events: int
    net_profit: FinancialAmount


class ExecutiveDashboardResponse(DashboardResponseModel):
    period: str
    net_profit_by_month: tuple[MonthlyProfitResponse, ...]
    net_profit_comparison: ProfitComparisonResponse
    events_by_package: tuple[PackageMetricResponse, ...]
    events_by_theme: tuple[ThemeMetricResponse, ...]
    top_extras: tuple[ExtraRankingResponse, ...]
    events_by_district: tuple[DistrictMetricResponse, ...]
