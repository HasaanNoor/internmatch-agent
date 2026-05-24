from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APPLICATIONS_PATH = PROJECT_ROOT / "data" / "applications.csv"

APPLICATION_COLUMNS = [
    "date_added",
    "company",
    "title",
    "location",
    "url",
    "fit_score",
    "ai_ds_alignment",
    "visa_risk",
    "recommended_action",
    "application_status",
    "notes",
]


def load_applications() -> pd.DataFrame:
    if not APPLICATIONS_PATH.exists() or APPLICATIONS_PATH.stat().st_size == 0:
        return pd.DataFrame(columns=APPLICATION_COLUMNS)

    applications = pd.read_csv(APPLICATIONS_PATH)
    for column in APPLICATION_COLUMNS:
        if column not in applications.columns:
            applications[column] = ""

    return applications[APPLICATION_COLUMNS]


def application_exists(url: str) -> bool:
    cleaned_url = str(url or "").strip()
    if not cleaned_url:
        return False

    applications = load_applications()
    if applications.empty:
        return False

    return applications["url"].fillna("").astype(str).str.strip().eq(cleaned_url).any()


def save_application(
    company: str = "",
    title: str = "",
    location: str = "",
    url: str = "",
    fit_score: Any = "",
    ai_ds_alignment: str = "",
    visa_risk: str = "",
    recommended_action: str = "",
    application_status: str = "Saved",
    notes: str = "",
) -> bool:
    cleaned_url = str(url or "").strip()
    if application_exists(cleaned_url):
        return False

    application = {
        "date_added": date.today().isoformat(),
        "company": str(company or "").strip(),
        "title": str(title or "").strip(),
        "location": str(location or "").strip(),
        "url": cleaned_url,
        "fit_score": fit_score,
        "ai_ds_alignment": str(ai_ds_alignment or "").strip(),
        "visa_risk": str(visa_risk or "").strip(),
        "recommended_action": str(recommended_action or "").strip(),
        "application_status": str(application_status or "Saved").strip(),
        "notes": str(notes or "").strip(),
    }

    applications = load_applications()
    updated_applications = pd.concat(
        [applications, pd.DataFrame([application], columns=APPLICATION_COLUMNS)],
        ignore_index=True,
    )

    APPLICATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    updated_applications.to_csv(APPLICATIONS_PATH, index=False)
    return True
