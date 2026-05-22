# AI Internship Agent - Development Rules

## Project Goal
Build an AI-powered internship assistant for:
- internship discovery
- resume matching
- AI summarization
- outreach generation
- recruiter email summarization
- reminders/workflows
- dashboarding

## Tech Stack
- Python
- Streamlit
- OpenAI API
- pandas
- dotenv

## Architecture Rules
- Keep modules small and modular
- Avoid duplicate business logic
- Use structured JSON outputs where possible
- Do not hardcode user-specific data
- Keep prompts separated into /prompts
- Avoid giant monolithic functions
- Add error handling
- Prefer readability over cleverness

## Important Constraints
- Do NOT auto-apply to jobs
- Do NOT expose API keys
- Preserve LaTeX resume formatting
- Use config.py for preferences/settings

## Preferred Workflow
job ingestion
→ summarization
→ eligibility analysis
→ resume matching
→ outreach generation
→ tracker/dashboard
