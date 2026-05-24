import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

from src.config import DEFAULT_MODEL


load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESUME_PATH = PROJECT_ROOT / "data" / "master_resume.tex"

MATCH_SCHEMA: dict[str, Any] = {
    "fit_score": 0,
    "matched_skills": [],
    "missing_skills": [],
    "strongest_resume_sections": [],
    "suggested_resume_edits": [],
    "recommended_action": "",
}


class ResumeMatcherError(RuntimeError):
    """Raised when resume matching cannot be completed."""


def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ResumeMatcherError("OPENAI_API_KEY is not set. Add it to your environment or .env file.")

    return OpenAI(api_key=api_key)


def read_resume_tex(resume_path: str | Path = DEFAULT_RESUME_PATH) -> str:
    path = Path(resume_path)
    if not path.exists():
        raise ResumeMatcherError(f"Resume file not found: {path}")

    try:
        resume_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ResumeMatcherError(f"Could not read resume file: {path}") from exc

    if not resume_text.strip():
        raise ResumeMatcherError(f"Resume file is empty: {path}")

    return resume_text


def clean_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def serialize_job_summary(job_summary: dict[str, Any] | str) -> str:
    if isinstance(job_summary, dict):
        return json.dumps(job_summary, indent=2)

    return clean_text(job_summary)


def build_match_prompt(job_summary: dict[str, Any] | str, job_description: str, resume_tex: str) -> str:
    return f"""
You are a resume-to-internship matching assistant.

Compare the candidate's LaTeX master resume against both the structured job summary and full job
description. Use only evidence from the resume and job text. Do not invent candidate experience.
Preserve LaTeX formatting in suggested edits by describing where edits should be made rather than
rewriting the entire resume.

Return ONLY valid JSON with this exact structure:
{json.dumps(MATCH_SCHEMA, indent=2)}

Field rules:
- fit_score must be an integer from 0 to 100.
- matched_skills should list skills, tools, domains, or responsibilities clearly supported by the resume.
- missing_skills should list important job requirements not clearly supported by the resume.
- strongest_resume_sections should identify the resume sections, roles, projects, or bullets that best match the job.
- suggested_resume_edits should be concise, actionable edits to improve fit while preserving truthfulness.
- recommended_action must be one of: "Apply", "Tailor resume then apply", "Network before applying", "Skip".

Scoring guidance:
- 85-100: strong direct match with most required skills present.
- 70-84: good match with minor tailoring or gaps.
- 50-69: partial match with several important gaps.
- 0-49: weak match or major mismatch.

Job summary:
{serialize_job_summary(job_summary)}

Job description:
{clean_text(job_description)}

Candidate master resume LaTeX:
{resume_tex}
""".strip()


def parse_json_response(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ResumeMatcherError("OpenAI returned invalid JSON for the resume match.") from exc

    if not isinstance(parsed, dict):
        raise ResumeMatcherError("OpenAI returned an unexpected resume match format.")

    return parsed


def ensure_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    if isinstance(value, str) and value.strip():
        return [value.strip()]

    return []


def normalize_fit_score(value: Any) -> int:
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        return 0

    return max(0, min(100, score))


def normalize_recommended_action(value: Any, fit_score: int) -> str:
    allowed_actions = {
        "Apply",
        "Tailor resume then apply",
        "Network before applying",
        "Skip",
    }
    action = str(value or "").strip()
    if action in allowed_actions:
        return action

    if fit_score >= 85:
        return "Apply"
    if fit_score >= 60:
        return "Tailor resume then apply"
    if fit_score >= 45:
        return "Network before applying"
    return "Skip"


def normalize_match_result(result: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(MATCH_SCHEMA)
    normalized.update(result)

    normalized["fit_score"] = normalize_fit_score(normalized.get("fit_score"))

    for key in (
        "matched_skills",
        "missing_skills",
        "strongest_resume_sections",
        "suggested_resume_edits",
    ):
        normalized[key] = ensure_list(normalized.get(key))

    normalized["recommended_action"] = normalize_recommended_action(
        normalized.get("recommended_action"),
        normalized["fit_score"],
    )

    return normalized


def match_resume(
    job_summary: dict[str, Any] | str,
    job_description: str,
    resume_path: str | Path = DEFAULT_RESUME_PATH,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    if not serialize_job_summary(job_summary):
        raise ResumeMatcherError("Missing job summary for resume matching.")

    if not clean_text(job_description):
        raise ResumeMatcherError("Missing job description for resume matching.")

    resume_tex = read_resume_tex(resume_path)
    prompt = build_match_prompt(job_summary, job_description, resume_tex)

    try:
        response = get_openai_client().chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You compare LaTeX resumes to internship postings and return strict JSON.",
                },
                {"role": "user", "content": prompt},
            ],
        )
    except OpenAIError as exc:
        raise ResumeMatcherError(f"OpenAI resume matching failed: {exc}") from exc

    content = response.choices[0].message.content
    if not content:
        raise ResumeMatcherError("OpenAI returned an empty resume match.")

    return normalize_match_result(parse_json_response(content))


def analyze_resume_match(
    job_summary: dict[str, Any] | str,
    job_description: str,
    resume_path: str | Path = DEFAULT_RESUME_PATH,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    return match_resume(
        job_summary=job_summary,
        job_description=job_description,
        resume_path=resume_path,
        model=model,
    )
