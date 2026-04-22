"""Shared UI option lists."""

SKILL_OPTIONS: list[tuple[str, str]] = [
    ("water_rescue", "Water rescue"),
    ("medical_assistance", "Medical assistance"),
    ("heavy_lifting", "Heavy lifting"),
    ("food_distribution", "Food distribution"),
    ("teaching", "Teaching"),
    ("translation", "Translation"),
    ("logistics", "Logistics"),
    ("data_entry", "Data entry"),
]

ROLE_OPTIONS: list[tuple[str, str]] = [
    ("volunteer", "Volunteer"),
    ("coordinator", "Coordinator"),
]

TASK_STATUSES = {"open", "pending", "closed", "completed", "cancelled"}
ASSIGNMENT_ACTIONS = {"approve", "reject", "complete"}
