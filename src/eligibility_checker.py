from openai import OpenAI
from dotenv import load_dotenv
import os
import json

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def analyze_eligibility(job_description):

    prompt = f"""
    You are an AI internship evaluation assistant for a graduate Computer Science student.

    The student:
    - is pursuing a Master's in Computer Science
    - is interested in Artificial Intelligence, Machine Learning, and Data Science
    - prefers internships related to:
        - AI Engineering
        - Machine Learning
        - Data Science
        - Data Analytics
        - AI Infrastructure
        - Applied AI
        - Intelligent Automation
        - Software Engineering roles with strong AI/data focus
    - prefers opportunities in:
        - Research Triangle area in North Carolina
        - Remote positions
        - East Coast technology hubs
    - is an F-1 international student requiring CPT/OPT compatibility

    Analyze this internship/job posting and determine:

    1. Whether CPT/OPT students are likely eligible
    2. Whether sponsorship restrictions exist
    3. Whether US citizenship or security clearance is required
    4. Whether the role strongly aligns with the student's AI/Data Science interests
    5. Whether the location preference aligns well
    6. Risk level:
        - Low
        - Medium
        - High

    Return ONLY valid JSON in this format:

    {{
        "AI_DS_Alignment": "",
        "Location_Alignment": "",
        "CPT_OPT_Eligibility": "",
        "Sponsorship_Restrictions": "",
        "US_Citizenship_Security_Clearance": "",
        "Risk_Level": ""
    }}

    Job Description:
    {job_description}
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "You are an expert immigration-aware internship analyzer."},
            {"role": "user", "content": prompt}
        ]
    )

    content = response.choices[0].message.content

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return content
    
