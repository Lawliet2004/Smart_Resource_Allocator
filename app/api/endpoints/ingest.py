from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi.errors import RateLimitExceeded
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.organization import Organization
from app.models.task import Task
from app.schemas.ingest import IngestRequest, IngestResponse
from app.services.extractor import extract_task_data
from app.services.matcher import find_best_volunteers
from app.web.deps import get_current_user
from app.web.rate_limit import limiter, user_or_ip_key

router = APIRouter()


@router.post("/", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.INGEST_RATE_LIMIT, key_func=user_or_ip_key)
def ingest_field_report(
    request: Request,
    payload: IngestRequest,
    db: Session = Depends(get_db),
):
    """
    Ingest an unstructured field report, extract data, create a Task, and match volunteers.
    """
    user = get_current_user(request, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    if user.role != "coordinator":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Coordinator role required.",
        )

    # Shared helper (avoid duplicating skill normalization with the web path).
    from app.web.coordinator import normalize_skills

    try:
        # 1. Extract structured data from raw text
        extracted_data = extract_task_data(payload.raw_text)
        organization = db.scalar(select(Organization).where(Organization.created_by_id == user.id))

        # 2. Create and save the Task
        new_task = Task(
            org_id=organization.id if organization is not None else None,
            created_by_id=user.id,
            raw_text=None,
            title=extracted_data["title"],
            description=extracted_data["description"],
            location=extracted_data["location"],
            urgency=extracted_data["urgency"],
            required_skills=normalize_skills(extracted_data["required_skills"]),
            status="open",
        )
        db.add(new_task)
        db.flush()
        db.refresh(new_task)

        # 3. Match volunteers
        matched = find_best_volunteers(new_task, db)
        db.commit()

        return IngestResponse(task=new_task, matched_volunteers=matched)
    except (HTTPException, RateLimitExceeded):
        # Let FastAPI / slowapi handlers convert these to proper 4xx responses.
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to process field report.",
        ) from e
