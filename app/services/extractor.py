import logging
import re

from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.skills import normalize_skills

logger = logging.getLogger(__name__)

MAX_TITLE_CHARS = 255
MAX_LOCATION_CHARS = 255
MAX_PEOPLE_NEEDED = 10_000


class TaskExtraction(BaseModel):
    title: str = Field(
        description="A short, descriptive title for the task "
        "(e.g., 'Medical Assistance Needed in Downtown')"
    )
    description: str = Field(
        description="A detailed description of the task based on the field report"
    )
    location: str = Field(
        description="The extracted location (e.g., 'Downtown', 'North Side', etc.) "
        "or 'Unknown' if not found"
    )
    urgency: int = Field(description="An urgency score from 1 (low) to 5 (high)")
    people_needed: int = Field(
        description="The number of people needed (capacity) inferred from the text. "
        "Default to 1 if unspecified."
    )
    required_skills: list[str] = Field(
        description="A list of required skills inferred from the text "
        "(e.g., 'water_rescue', 'medical_assistance', 'heavy_lifting')"
    )


def _mock_extract(raw_text: str) -> dict:
    """Mock fallback using simple keyword matching."""
    text = raw_text.casefold()

    urgency = 1
    people_needed = 1
    skills: list[str] = []
    location = "Unknown"
    title = "Field Report"

    if any(re.search(pattern, text) for pattern in [r"\burgent\b", r"\bemergency\b"]):
        urgency = 5
        title = "Urgent Field Report"

    # Mock people needed inference
    team_patterns = [r"\bteam\b", r"\bgroup\b", r"\bmany\b", r"\bseveral\b"]
    if any(re.search(pattern, text) for pattern in team_patterns):
        people_needed = 5
    elif re.search(r"\b(\d+)\b\s*people", text):
        match = re.search(r"\b(\d+)\b\s*people", text)
        if match:
            people_needed = int(match.group(1))
    if any(re.search(pattern, text) for pattern in [r"\bflood(?:s|ed|ing)?\b", r"\bwater\b"]):
        skills.append("water_rescue")

    medical_patterns = [r"\bmedical\b", r"\bdoctors?\b", r"\binjured\b"]
    if any(re.search(pattern, text) for pattern in medical_patterns):
        skills.append("medical_assistance")

    if any(re.search(pattern, text) for pattern in [r"\bdebris\b", r"\bclear(?:ing)?\b"]):
        skills.append("heavy_lifting")

    if re.search(r"\bdowntown\b", text):
        location = "Downtown"
    elif re.search(r"\bnorth\b", text):
        location = "North Side"
    elif re.search(r"\bsouth\b", text):
        location = "South Side"

    summary_parts = ["Auto-extracted task from coordinator field report."]
    if location != "Unknown":
        summary_parts.append(f"Location hint: {location}.")
    if skills:
        summary_parts.append(f"Required skills: {', '.join(skills)}.")
    if urgency >= 4:
        summary_parts.append("High urgency reported.")

    return {
        "title": title,
        "description": " ".join(summary_parts),
        "location": location,
        "urgency": urgency,
        "people_needed": people_needed,
        "required_skills": skills,
    }


def _coerce_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def sanitize_extraction(data: dict) -> dict:
    """Clamp extractor output to what the database and UI can accept.

    The Gemini path returns model-authored values: a 5,000-character title or an
    urgency of 9 would otherwise reach the Task insert and fail (or render
    badly). The mock path is passed through the same guard so both behave
    identically.
    """
    title = str(data.get("title") or "").strip() or "Field Report"
    location = str(data.get("location") or "").strip() or "Unknown"
    return {
        "title": title[:MAX_TITLE_CHARS],
        "description": str(data.get("description") or "").strip() or None,
        "location": location[:MAX_LOCATION_CHARS],
        "urgency": _coerce_int(data.get("urgency"), default=1, minimum=1, maximum=5),
        "people_needed": _coerce_int(
            data.get("people_needed"), default=1, minimum=1, maximum=MAX_PEOPLE_NEEDED
        ),
        "required_skills": normalize_skills(data.get("required_skills")),
    }


def extract_task_data(raw_text: str) -> dict:
    """
    Extract structured task data from raw field report using Gemini if configured,
    falling back to mock extraction otherwise.
    """
    if not settings.GEMINI_API_KEY:
        logger.info("GEMINI_API_KEY not set. Using mock extractor.")
        return sanitize_extraction(_mock_extract(raw_text))

    try:
        from google import genai

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=f"Extract task details from this field report:\n\n{raw_text}",
            config={
                'response_mime_type': 'application/json',
                'response_schema': TaskExtraction,
            },
        )

        if response.text:
            extracted = TaskExtraction.model_validate_json(response.text).model_dump()
            return sanitize_extraction(extracted)

    except Exception:
        logger.exception("Failed to use Gemini for extraction. Falling back to mock extractor.")

    return sanitize_extraction(_mock_extract(raw_text))
