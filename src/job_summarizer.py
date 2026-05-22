import json
import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError


load_dotenv()

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


class JobSummarizerError(RuntimeError):
    """Raised when a job summary cannot be generated."""


SUMMARY_SCHEMA: dict[str, Any] = {
    "company": "",
    "title": "",
    "location": "",
    "location_type": "Unknown",
    "responsibilities": [],
    "required_skills": [],
    "preferred_skills": [],
    "visa_related_language": {
        "mentions": [],
        "cpt_opt_signal": "Unknown",
        "sponsorship_signal": "Unknown",
        "citizenship_or_clearance_signal": "Unknown",
    },
    "ai_data_science_relevance": {
        "level": "Unknown",
        "reasoning": "",
        "keywords": [],
    },
    "summary": "",
}


def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise JobSummarizerError("OPENAI_API_KEY is not set. Add it to your environment or .env file.")

    return OpenAI(api_key=api_key)


def build_summary_prompt(job_posting: dict[str, str]) -> str:
    return f"""
You are an internship job-posting parser. Extract factual details from the posting and infer missing
company, title, and location only when the text gives enough evidence. If evidence is weak, use "Unknown".

Return ONLY valid JSON with this exact structure:
{json.dumps(SUMMARY_SCHEMA, indent=2)}

Rules:
- Keep lists concise, using short phrases instead of full paragraphs.
- location_type must be one of: "Remote", "Hybrid", "On-site", "Multiple", "Unknown".
- visa_related_language.mentions should quote or closely paraphrase only the visa, sponsorship,
  work authorization, citizenship, or clearance language present in the posting.
- cpt_opt_signal must be one of: "Likely compatible", "Possibly compatible", "Likely not compatible", "Unknown".
- sponsorship_signal must be one of: "No restriction found", "Restriction found", "Sponsorship available", "Unknown".
- citizenship_or_clearance_signal must be one of: "Required", "Not mentioned", "Unknown".
- ai_data_science_relevance.level must be one of: "High", "Medium", "Low", "Unknown".

Provided hints:
Company: {job_posting.get("company_hint") or "Not provided"}
Title: {job_posting.get("title_hint") or "Not provided"}
Location: {job_posting.get("location_hint") or "Not provided"}
URL: {job_posting.get("job_url") or "Not provided"}

Job description:
{job_posting.get("raw_description", "")}
""".strip()


def parse_json_response(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise JobSummarizerError("OpenAI returned invalid JSON for the job summary.") from exc

    if not isinstance(parsed, dict):
        raise JobSummarizerError("OpenAI returned an unexpected summary format.")

    return parsed


def ensure_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    if isinstance(value, str) and value.strip():
        return [value.strip()]

    return []


def normalize_summary(summary: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(SUMMARY_SCHEMA)
    normalized.update(summary)

    for key in ("company", "title", "location", "location_type", "summary"):
        normalized[key] = str(normalized.get(key) or "Unknown").strip() or "Unknown"

    for key in ("responsibilities", "required_skills", "preferred_skills"):
        normalized[key] = ensure_list(normalized.get(key))

    visa_defaults = SUMMARY_SCHEMA["visa_related_language"]
    visa_data = normalized.get("visa_related_language")
    if not isinstance(visa_data, dict):
        visa_data = {}
    normalized["visa_related_language"] = {
        "mentions": ensure_list(visa_data.get("mentions")),
        "cpt_opt_signal": str(visa_data.get("cpt_opt_signal") or visa_defaults["cpt_opt_signal"]),
        "sponsorship_signal": str(visa_data.get("sponsorship_signal") or visa_defaults["sponsorship_signal"]),
        "citizenship_or_clearance_signal": str(
            visa_data.get("citizenship_or_clearance_signal")
            or visa_defaults["citizenship_or_clearance_signal"]
        ),
    }

    relevance_defaults = SUMMARY_SCHEMA["ai_data_science_relevance"]
    relevance_data = normalized.get("ai_data_science_relevance")
    if not isinstance(relevance_data, dict):
        relevance_data = {}
    normalized["ai_data_science_relevance"] = {
        "level": str(relevance_data.get("level") or relevance_defaults["level"]),
        "reasoning": str(relevance_data.get("reasoning") or "").strip(),
        "keywords": ensure_list(relevance_data.get("keywords")),
    }

    return normalized


def summarize_job(job_posting: dict[str, str], model: str = DEFAULT_MODEL) -> dict[str, Any]:
    if not job_posting.get("raw_description"):
        raise JobSummarizerError("Missing job description text for summarization.")

    prompt = build_summary_prompt(job_posting)

    try:
        response = get_openai_client().chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You extract structured internship/job posting data as strict JSON.",
                },
                {"role": "user", "content": prompt},
            ],
        )
    except OpenAIError as exc:
        raise JobSummarizerError(f"OpenAI job summarization failed: {exc}") from exc

    content = response.choices[0].message.content
    if not content:
        raise JobSummarizerError("OpenAI returned an empty job summary.")

    return normalize_summary(parse_json_response(content))
