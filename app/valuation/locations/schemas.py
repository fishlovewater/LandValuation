from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class LocationCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    label: str = Field(min_length=1, max_length=120)
    address: str | None = Field(default=None, max_length=300)

class LocationUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    label: str | None = Field(default=None, min_length=1, max_length=120)
    address: str | None = Field(default=None, max_length=300)

class LocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    location_id: UUID
    case_id: UUID
    display_order: int
    label: str
    address: str | None
    is_benchmark_location: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime