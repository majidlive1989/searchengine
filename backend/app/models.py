from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TravelSpec(Strict):
    intent: Literal["FLIGHT_SEARCH", "HOTEL_SEARCH", "PACKAGE_SEARCH"] = (
        "PACKAGE_SEARCH"
    )
    origin: str = Field(default="", max_length=3)
    destination: str = Field(default="", max_length=3)
    departure_date: date | None = None
    return_date: date | None = None
    adults: int = Field(default=1, ge=1, le=9)
    children: int = Field(default=0, ge=0, le=8)
    rooms: int = Field(default=1, ge=1, le=5)
    stars_min: int = Field(default=3, ge=1, le=5)
    direct_only: bool = False
    cabin: Literal["ECONOMY", "BUSINESS"] = "ECONOMY"

    def issues(self):
        issues = []
        # The pilot intentionally resolves a bounded airport dictionary.
        airports = {
            "IKA",
            "THR",
            "MCT",
            "DXB",
            "IST",
            "DOH",
            "AUH",
            "LHR",
            "CDG",
            "MHD",
            "SYZ",
            "TBS",
            "GYD",
        }
        if self.intent != "HOTEL_SEARCH" and self.origin not in airports:
            issues.append("Select a supported origin airport")
        if self.destination not in airports:
            issues.append("Select a supported destination airport")
        if self.intent != "HOTEL_SEARCH" and self.origin == self.destination:
            issues.append("Origin and destination must differ")
        if not self.departure_date:
            issues.append("Departure / check-in date is required")
        elif self.departure_date < datetime.now(timezone.utc).date():
            issues.append("Departure date cannot be in the past")
        if self.intent != "FLIGHT_SEARCH" and not self.return_date:
            issues.append("Check-out date is required")
        if (
            self.departure_date
            and self.return_date
            and self.return_date <= self.departure_date
        ):
            issues.append("Return / check-out must be after departure")
        if self.children:
            issues.append(
                "Child fares require ages; this pilot supports adult-only searches"
            )
        if self.adults < self.rooms and self.intent != "FLIGHT_SEARCH":
            issues.append("Each room needs at least one adult")
        return issues


class RequestIn(Strict):
    customer_name: str = Field(min_length=1, max_length=100)
    text: str = Field(default="", max_length=6000)
    spec: TravelSpec = Field(default_factory=TravelSpec)


class TextIn(Strict):
    text: str = Field(min_length=1, max_length=6000)


class ConfirmIn(Strict):
    spec: TravelSpec
    revision: int


class SearchIn(Strict):
    source_ids: list[str] = Field(min_length=1, max_length=10)


class OfferIn(Strict):
    request_id: str
    result_ids: list[str] = Field(min_length=1, max_length=2)
    markup_type: Literal["PERCENT", "FIXED"] = "PERCENT"
    markup: Decimal = Field(ge=0, le=100000, max_digits=12, decimal_places=3)
    note: str = Field(default="", max_length=1000)


class LoginIn(Strict):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class UserIn(LoginIn):
    name: str = Field(min_length=1, max_length=100)
    role: Literal["ADMIN", "MANAGER", "AGENT"]


class SourceIn(Strict):
    name: str = Field(min_length=2, max_length=80)
    kind: Literal["FLIGHT", "HOTEL"]
    provider: Literal["DEMO", "HTTP_BRIDGE", "JSON_API", "MANUAL"] = "JSON_API"
    account_ref: str = Field(default="", max_length=100, pattern=r"^[a-zA-Z0-9_.-]*$")
    classification: Literal["CERTIFIED", "AGENCY_TAUGHT"] = "AGENCY_TAUGHT"
    notes: str = Field(default="", max_length=1000)


class WorkflowIn(Strict):
    mapping_version: str = Field(
        min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$"
    )
    notes: str = Field(default="", max_length=2000)


class TestIn(Strict):
    spec: TravelSpec


class TransitionIn(Strict):
    state: Literal[
        "WAITING_CUSTOMER", "WON", "LOST", "CANCELLED", "ON_HOLD", "SALES_REVIEW"
    ]
    reason: str = Field(min_length=3, max_length=500)


class Rate(Strict):
    external_id: str = Field(min_length=1, max_length=200)
    kind: Literal["FLIGHT", "HOTEL"]
    title: str = Field(min_length=1, max_length=200)
    origin: str = Field(default="", max_length=3)
    destination: str = Field(min_length=3, max_length=3)
    departure_date: date
    return_date: date | None
    adults: int = Field(ge=1, le=9)
    rooms: int = Field(ge=1, le=5)
    cabin: Literal["ECONOMY", "BUSINESS"]
    net_price: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    currency: Literal["USD", "EUR", "AED", "OMR", "IRR", "GBP"]
    price_basis: Literal["TOTAL_PARTY_STAY_TAX_INCLUDED"]
    stops: int = Field(ge=0, le=5)
    stars: int = Field(ge=0, le=5)
    details: str = Field(min_length=1, max_length=1000)
    cancellation_policy: str = Field(min_length=1, max_length=2000)
    captured_at: datetime
    expires_at: datetime
    demo: bool

    @model_validator(mode="after")
    def check_freshness(self):
        if not self.captured_at.tzinfo or not self.expires_at.tzinfo:
            raise ValueError("Timezone required")
        if self.expires_at <= self.captured_at:
            raise ValueError("Invalid rate validity")
        if (self.expires_at - self.captured_at).total_seconds() > 900:
            raise ValueError("Rate validity exceeds pilot policy")
        return self


class ExecutionResult(Strict):
    job_id: str
    status: Literal["SUCCESS", "FAILED", "RECONNECT_REQUIRED", "NEEDS_REVIEW"]
    records: list[Rate] = Field(default_factory=list, max_length=100)
    error_code: str | None = None
    output_schema_version: Literal["1.0"] = "1.0"
