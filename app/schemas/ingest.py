from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import settings


class IngestRequest(BaseModel):
    raw_text: str = Field(min_length=1, max_length=settings.MAX_INGEST_CHARS)

    @field_validator("raw_text")
    @classmethod
    def non_empty_raw_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("raw_text cannot be empty")
        return cleaned


class IngestTaskResponse(BaseModel):
    id: int
    title: str
    description: str | None = None
    location: str | None = None
    urgency: int
    required_skills: list[str] = Field(default_factory=list)
    status: str

    model_config = ConfigDict(from_attributes=True)


class IngestVolunteerResponse(BaseModel):
    id: int
    name: str
    location: str | None = None
    skills: list[str] = Field(default_factory=list)
    is_available: bool

    model_config = ConfigDict(from_attributes=True)


class IngestResponse(BaseModel):
    task: IngestTaskResponse
    matched_volunteers: list[IngestVolunteerResponse]
