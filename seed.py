"""Seed the database with a handful of test volunteers."""

from app.core.database import SessionLocal
from app.models.volunteer import Volunteer

SAMPLE_VOLUNTEERS = [
    {
        "name": "Alice Smith",
        "phone_number": "555-0101",
        "location": "Downtown",
        "skills": ["water_rescue", "medical_assistance"],
        "is_available": True,
    },
    {
        "name": "Bob Johnson",
        "phone_number": "555-0102",
        "location": "North Side",
        "skills": ["heavy_lifting"],
        "is_available": True,
    },
    {
        "name": "Charlie Davis",
        "phone_number": "555-0103",
        "location": "Downtown",
        "skills": ["heavy_lifting"],
        "is_available": True,
    },
    {
        "name": "Diana Prince",
        "phone_number": "555-0104",
        "location": "South Side",
        "skills": ["medical_assistance", "water_rescue"],
        "is_available": True,
    },
    {
        "name": "Eve Adams",
        "phone_number": "555-0105",
        "location": "Downtown",
        "skills": ["water_rescue"],
        "is_available": False,
    },
]


def seed_data() -> None:
    db = SessionLocal()
    try:
        if db.query(Volunteer).count() > 0:
            print("Database already seeded with volunteers.")
            return

        db.add_all([Volunteer(**v) for v in SAMPLE_VOLUNTEERS])
        db.commit()
        print(f"Successfully added {len(SAMPLE_VOLUNTEERS)} test volunteers.")
    except Exception as e:
        print(f"An error occurred: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    seed_data()
