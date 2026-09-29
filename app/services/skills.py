"""Canonical skill vocabulary and normalization helpers.

This is the single source of truth for skills. The web layer re-exports
``SKILL_OPTIONS`` for its select inputs, and both the web and API ingest paths
use ``normalize_skills`` so a task created through either route stores exactly
the same values.
"""

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

VALID_SKILLS: frozenset[str] = frozenset(value for value, _label in SKILL_OPTIONS)

SKILL_LABELS: dict[str, str] = dict(SKILL_OPTIONS)


def normalize_skills(skills: list[str] | None) -> list[str]:
    """Keep only known skills, de-duplicated, in first-seen order."""
    deduped: list[str] = []
    seen: set[str] = set()
    for skill in skills or []:
        if not isinstance(skill, str):
            continue
        candidate = skill.strip()
        if candidate in VALID_SKILLS and candidate not in seen:
            deduped.append(candidate)
            seen.add(candidate)
    return deduped


def normalized_skill_set(skills: list[object] | None) -> set[str]:
    """Case-folded set of non-empty skill strings, for intersection checks."""
    return {
        skill.strip().casefold()
        for skill in (skills or [])
        if isinstance(skill, str) and skill.strip()
    }


def skill_label(value: str) -> str:
    return SKILL_LABELS.get(value, value.replace("_", " ").title())
