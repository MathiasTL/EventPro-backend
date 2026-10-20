from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, model_validator

from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.financial_reporting import AccountingPeriod, PeriodType

FinancialAmount = Annotated[
    Decimal,
    Field(allow_inf_nan=False),
    PlainSerializer(lambda value: float(value), float, when_used="json"),
]


class FinancialPnlQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_type: PeriodType = Field(description="MONTHLY o WEEKLY (semana ISO).")
    year: int = Field(ge=1, le=9998, description="Año calendario o año ISO, según period_type.")
    month: int | None = Field(default=None, ge=1, le=12)
    week: int | None = Field(default=None, ge=1, le=53)

    @model_validator(mode="after")
    def validate_period(self) -> "FinancialPnlQuery":
        try:
            AccountingPeriod.create(self.period_type, self.year, month=self.month, week=self.week)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
        return self


class FinancialDirectCostsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fixed_packages_cost: FinancialAmount
    fixed_extras_cost: FinancialAmount
    mobility_operational_cost: FinancialAmount
    total_costs: FinancialAmount


class FinancialPnlResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    period: str
    total_events_settled: int
    gross_revenue: FinancialAmount
    direct_costs: FinancialDirectCostsResponse
    net_profit: FinancialAmount
    profit_margin_percentage: FinancialAmount
