from pydantic import BaseModel, ConfigDict


class VolunteerBase(BaseModel):
    name: str
    phone_number: str | None = None
    location: str | None = None
    skills: list[str] = []
    is_available: bool = True

class VolunteerCreate(VolunteerBase):
    pass

class VolunteerResponse(VolunteerBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
