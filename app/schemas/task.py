from pydantic import BaseModel, ConfigDict, Field


class TaskBase(BaseModel):
    org_id: int | None = None
    created_by_id: int | None = None
    raw_text: str | None = None
    title: str
    description: str | None = None
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    urgency: int = 1
    required_skills: list[str] = Field(default_factory=list)
    status: str = "open"


class TaskCreate(TaskBase):
    pass


class TaskResponse(TaskBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
