from pydantic import BaseModel

from .task import TaskResponse
from .volunteer import VolunteerResponse


class IngestRequest(BaseModel):
    raw_text: str

class IngestResponse(BaseModel):
    task: TaskResponse
    matched_volunteers: list[VolunteerResponse]
