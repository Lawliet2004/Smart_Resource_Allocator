"""Unit tests for the pure matching / normalization logic (no database)."""

import pytest

from app.models.task import Task
from app.models.volunteer import Volunteer
from app.services.capacity import capacity_summary, task_capacity
from app.services.extractor import _mock_extract, sanitize_extraction
from app.services.scoring import is_eligible, match_score
from app.services.search import LIKE_ESCAPE_CHAR, like_pattern
from app.services.skills import normalize_skills, normalized_skill_set, skill_label


def make_task(**kwargs) -> Task:
    defaults = {
        "title": "Test task",
        "location": None,
        "urgency": 1,
        "people_needed": 1,
        "required_skills": [],
        "status": "open",
    }
    return Task(**{**defaults, **kwargs})


def make_volunteer(**kwargs) -> Volunteer:
    defaults = {"name": "Test volunteer", "skills": [], "location": None, "is_available": True}
    return Volunteer(**{**defaults, **kwargs})


# --- skills -----------------------------------------------------------------


def test_normalize_skills_drops_unknown_and_deduplicates():
    assert normalize_skills(["teaching", "not_a_skill", "teaching", "logistics"]) == [
        "teaching",
        "logistics",
    ]


def test_normalize_skills_tolerates_none_and_non_strings():
    assert normalize_skills(None) == []
    assert normalize_skills([None, 3, " teaching "]) == ["teaching"]


def test_normalized_skill_set_casefolds():
    assert normalized_skill_set(["Teaching", " LOGISTICS "]) == {"teaching", "logistics"}


def test_skill_label_falls_back_to_title_case():
    assert skill_label("water_rescue") == "Water rescue"
    assert skill_label("unmapped_skill") == "Unmapped Skill"


# --- eligibility & scoring --------------------------------------------------


def test_task_without_location_matches_any_volunteer():
    assert is_eligible(make_task(), make_volunteer(location="Anywhere"))


def test_unknown_location_is_treated_as_anywhere():
    task = make_task(location="Unknown")
    assert is_eligible(task, make_volunteer(location="Downtown"))


def test_located_task_requires_matching_volunteer_location():
    task = make_task(location="Downtown")
    assert is_eligible(task, make_volunteer(location="downtown"))  # case-insensitive
    assert not is_eligible(task, make_volunteer(location="North Side"))
    assert not is_eligible(task, make_volunteer(location=None))


def test_skill_requirement_needs_at_least_one_overlap():
    task = make_task(required_skills=["teaching", "logistics"])
    assert is_eligible(task, make_volunteer(skills=["logistics"]))
    assert not is_eligible(task, make_volunteer(skills=["water_rescue"]))
    assert not is_eligible(task, make_volunteer(skills=[]))


def test_score_rewards_overlap_location_availability_and_urgency():
    task = make_task(required_skills=["teaching", "logistics"], location="Downtown", urgency=5)
    both = make_volunteer(skills=["teaching", "logistics"], location="Downtown")
    one = make_volunteer(skills=["teaching"], location="Downtown")
    elsewhere = make_volunteer(skills=["teaching"], location="North Side")
    busy = make_volunteer(skills=["teaching"], location="Downtown", is_available=False)

    assert match_score(task, both) > match_score(task, one)
    assert match_score(task, one) > match_score(task, elsewhere)
    assert match_score(task, one) > match_score(task, busy)


def test_score_clamps_out_of_range_urgency():
    volunteer = make_volunteer()
    assert match_score(make_task(urgency=99), volunteer) == match_score(
        make_task(urgency=5), volunteer
    )
    assert match_score(make_task(urgency=0), volunteer) == match_score(
        make_task(urgency=1), volunteer
    )


# --- capacity ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("needed", "filled", "expected_remaining", "expected_full"),
    [(1, 0, 1, False), (1, 1, 0, True), (3, 1, 2, False), (3, 5, 0, True), (0, 0, 1, False)],
)
def test_capacity_summary(needed, filled, expected_remaining, expected_full):
    summary = capacity_summary(make_task(people_needed=needed), filled)
    assert summary["remaining"] == expected_remaining
    assert summary["is_full"] is expected_full
    assert summary["filled"] <= summary["needed"]


def test_task_capacity_is_at_least_one():
    assert task_capacity(make_task(people_needed=0)) == 1
    assert task_capacity(make_task(people_needed=None)) == 1


# --- search -----------------------------------------------------------------


def test_like_pattern_escapes_wildcards():
    assert like_pattern("100%") == "%100\\%%"
    assert like_pattern("a_b") == "%a\\_b%"
    assert like_pattern(LIKE_ESCAPE_CHAR) == "%\\\\%"


def test_like_pattern_wraps_plain_text():
    assert like_pattern("park") == "%park%"


# --- extractor --------------------------------------------------------------


def test_mock_extract_detects_urgency_skills_and_location():
    result = sanitize_extraction(_mock_extract("Urgent flooding downtown, injured people"))
    assert result["urgency"] == 5
    assert result["location"] == "Downtown"
    assert "water_rescue" in result["required_skills"]
    assert "medical_assistance" in result["required_skills"]


def test_sanitize_clamps_model_authored_values():
    result = sanitize_extraction(
        {
            "title": "T" * 500,
            "description": "  ",
            "location": "L" * 500,
            "urgency": 99,
            "people_needed": -4,
            "required_skills": ["teaching", "hallucinated_skill"],
        }
    )
    assert len(result["title"]) == 255
    assert len(result["location"]) == 255
    assert result["description"] is None
    assert result["urgency"] == 5
    assert result["people_needed"] == 1
    assert result["required_skills"] == ["teaching"]


def test_sanitize_supplies_defaults_for_missing_fields():
    result = sanitize_extraction({})
    assert result["title"] == "Field Report"
    assert result["location"] == "Unknown"
    assert result["urgency"] == 1
    assert result["people_needed"] == 1
    assert result["required_skills"] == []


def test_sanitize_handles_non_numeric_urgency():
    assert sanitize_extraction({"urgency": "high"})["urgency"] == 1
