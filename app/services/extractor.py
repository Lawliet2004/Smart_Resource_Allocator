import re


def has_pattern(text: str, *patterns: str) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def extract_task_data(raw_text: str) -> dict:
    """
    Mock AI Extractor. Uses simple keyword matching to simulate AI parsing.
    """
    text = raw_text.casefold()

    # Defaults
    urgency = 1
    skills: list[str] = []
    location = "Unknown"
    title = "Field Report"
    
    if has_pattern(text, r"\burgent\b", r"\bemergency\b"):
        urgency = 5
        title = "Urgent Field Report"
    
    if has_pattern(text, r"\bflood(?:s|ed|ing)?\b", r"\bwater\b"):
        skills.append("water_rescue")
    
    if has_pattern(text, r"\bmedical\b", r"\bdoctors?\b", r"\binjured\b"):
        skills.append("medical_assistance")
        
    if has_pattern(text, r"\bdebris\b", r"\bclear(?:ing)?\b"):
        skills.append("heavy_lifting")
        
    if has_pattern(text, r"\bdowntown\b"):
        location = "Downtown"
    elif has_pattern(text, r"\bnorth\b"):
        location = "North Side"
    elif has_pattern(text, r"\bsouth\b"):
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
        "required_skills": skills,
    }
