from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.task import Task
from app.schemas.ingest import IngestRequest, IngestResponse
from app.services.extractor import extract_task_data
from app.services.matcher import find_best_volunteers

router = APIRouter()

@router.post("/", response_model=IngestResponse)
def ingest_field_report(request: IngestRequest, db: Session = Depends(get_db)):
    """
    Ingest an unstructured field report, extract data, create a Task, and match volunteers.
    """
    try:
        # 1. Extract structured data from raw text
        extracted_data = extract_task_data(request.raw_text)
        
        # 2. Create and save the Task
        new_task = Task(
            raw_text=request.raw_text,
            title=extracted_data["title"],
            description=extracted_data["description"],
            location=extracted_data["location"],
            urgency=extracted_data["urgency"],
            required_skills=extracted_data["required_skills"],
            status="pending"
        )
        db.add(new_task)
        db.commit()
        db.refresh(new_task)
        
        # 3. Match volunteers
        matched = find_best_volunteers(new_task, db)
        
        return IngestResponse(
            task=new_task,
            matched_volunteers=matched
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e
