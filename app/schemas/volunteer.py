from pydantic import BaseModel, ConfigDict, Field


class VolunteerBase(BaseModel):
    name: str
    phone_number: str | None = None
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    skills: list[str] = Field(default_factory=list)
    is_available: bool = True


class VolunteerCreate(VolunteerBase):
    pass


class VolunteerResponse(VolunteerBase):
    id: int
    user_id: int | None = None

    model_config = ConfigDict(from_attributes=True)
