def extract_task_data(raw_text: str) -> dict:
    """
    Mock AI Extractor. Uses simple keyword matching to simulate AI parsing.
    """
    text = raw_text.lower()
    
    # Defaults
    urgency = 1
    skills = []
    location = "Unknown"
    title = "Field Report"
    
    if "urgent" in text or "emergency" in text:
        urgency = 5
        title = "Urgent Field Report"
    
    if "flood" in text or "water" in text:
        skills.append("water_rescue")
    
    if "medical" in text or "doctor" in text or "injured" in text:
        skills.append("medical_assistance")
        
    if "debris" in text or "clear" in text:
        skills.append("heavy_lifting")
        
    if "downtown" in text:
        location = "Downtown"
    elif "north" in text:
        location = "North Side"
    elif "south" in text:
        location = "South Side"
        
    return {
        "title": title,
        "description": raw_text,
        "location": location,
        "urgency": urgency,
        "required_skills": skills
    }
