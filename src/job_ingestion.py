from dataclasses import dataclass
from typing import Any


class JobIngestionError(ValueError):
    """Raised when a pasted job description cannot be ingested."""


@dataclass(frozen=True)
class JobPosting:
    raw_description: str
    company_hint: str = ""
    title_hint: str = ""
    location_hint: str = ""
    job_url: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "raw_description": self.raw_description,
            "company_hint": self.company_hint,
            "title_hint": self.title_hint,
            "location_hint": self.location_hint,
            "job_url": self.job_url,
        }


def clean_text(value: Any) -> str:
    if value is None:
        return ""

    return " ".join(str(value).replace("\r\n", "\n").replace("\r", "\n").split())


def clean_multiline_text(value: Any) -> str:
    if value is None:
        return ""

    lines = [line.strip() for line in str(value).replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    cleaned_lines = [line for line in lines if line]
    return "\n".join(cleaned_lines).strip()


def ingest_job_description(
    job_description: str,
    company: str = "",
    title: str = "",
    location: str = "",
    job_url: str = "",
) -> dict[str, str]:
    raw_description = clean_multiline_text(job_description)

    if not raw_description:
        raise JobIngestionError("Please paste a job description before analyzing.")

    if len(raw_description) < 80:
        raise JobIngestionError("The pasted job description is too short to analyze reliably.")

    posting = JobPosting(
        raw_description=raw_description,
        company_hint=clean_text(company),
        title_hint=clean_text(title),
        location_hint=clean_text(location),
        job_url=clean_text(job_url),
    )

    return posting.to_dict()
