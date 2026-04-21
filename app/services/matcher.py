from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.volunteer import Volunteer


def find_best_volunteers(task: Task, db: Session) -> list[Volunteer]:
    """
    Matches volunteers to a task based on skills and location.
    This is a basic matching engine.
    """
    # Fetch all available volunteers
    stmt = select(Volunteer).where(Volunteer.is_available.is_(True))
    volunteers = db.execute(stmt).scalars().all()
    
    matched = []
    for vol in volunteers:
        # If task has a specific location, only match volunteers in that location
        if task.location and task.location != "Unknown":
            if vol.location and vol.location.lower() != task.location.lower():
                continue
            
        # If task requires skills, check if volunteer has any
        if task.required_skills:
            vol_skills = set(vol.skills) if vol.skills else set()
            req_skills = set(task.required_skills)
            if not vol_skills.intersection(req_skills):
                continue
                
        matched.append(vol)
        
    return matched
