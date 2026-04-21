from pydantic import BaseModel, ConfigDict


class TaskBase(BaseModel):
    raw_text: str | None = None
    title: str
    description: str | None = None
    location: str | None = None
    urgency: int = 1
    required_skills: list[str] = []
    status: str = "pending"

class TaskCreate(TaskBase):
    pass

class TaskResponse(TaskBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
