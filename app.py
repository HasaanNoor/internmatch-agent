import streamlit as st
from src.eligibility_checker import analyze_eligibility
from src.job_ingestion import JobIngestionError, ingest_job_description
from src.job_scraper import JobScraperError, scrape_job
from src.job_summarizer import JobSummarizerError, summarize_job
from src.tracker import application_exists, load_applications, save_application
import json
import traceback

st.title("AI Internship Agent")

analysis_tab, tracker_tab = st.tabs(["Analyze Internship", "Applications Tracker"])


def display_items(title, items):
    if items is None:
        items = []
    st.markdown(f"**{title}**")
    if items:
        for item in items:
            st.write(f"- {item}")
    else:
        st.caption("Not found in the posting.")


def display_job_summary(summary):
    if not summary:
        st.error("No summary data returned.")
        return

    st.subheader("Job Summary")

    col1, col2, col3, col4 = st.columns(4)
    col1.markdown("**Company**")
    col1.write(summary.get("company", "Unknown"))
    col2.markdown("**Title**")
    col2.write(summary.get("title", "Unknown"))
    col3.markdown("**Location**")
    col3.write(summary.get("location", "Unknown"))
    col4.markdown("**Type**")
    col4.write(summary.get("location_type", "Unknown"))

    if summary.get("summary"):
        st.write(summary["summary"])

    display_items("Responsibilities", summary.get("responsibilities", []))
    display_items("Required Skills", summary.get("required_skills", []))
    display_items("Preferred Skills", summary.get("preferred_skills", []))

    relevance = summary.get("ai_data_science_relevance") or {}
    st.markdown("**AI/Data Science Relevance**")
    st.write(f"Level: {relevance.get('level', 'Unknown')}")
    if relevance.get("reasoning"):
        st.write(relevance["reasoning"])
    if relevance.get("keywords"):
        st.write("Keywords: " + ", ".join(relevance["keywords"]))

    visa = summary.get("visa_related_language") or {}
    st.markdown("**Visa / Work Authorization Language**")
    st.write(f"CPT/OPT signal: {visa.get('cpt_opt_signal', 'Unknown')}")
    st.write(f"Sponsorship signal: {visa.get('sponsorship_signal', 'Unknown')}")
    st.write(f"Citizenship or clearance signal: {visa.get('citizenship_or_clearance_signal', 'Unknown')}")
    display_items("Mentions", visa.get("mentions", []))


def prepare_job_input(company, role, location, job_url, job_description):
    if job_url.strip():
        try:
            scraped_job = scrape_job(job_url)
            return {
                "company": company.strip() or scraped_job.get("company", ""),
                "role": role.strip() or scraped_job.get("title", ""),
                "location": location.strip() or scraped_job.get("location", ""),
                "job_url": scraped_job.get("url", job_url.strip()),
                "job_description": scraped_job.get("job_description", ""),
                "source": "automatic scraping",
                "warning": "",
            }
        except JobScraperError as e:
            if not job_description.strip():
                raise

            return {
                "company": company.strip(),
                "role": role.strip(),
                "location": location.strip(),
                "job_url": job_url.strip(),
                "job_description": job_description,
                "source": "manual input",
                "warning": f"Automatic scraping failed, so the pasted job description was used instead: {e}",
            }

    return {
        "company": company.strip(),
        "role": role.strip(),
        "location": location.strip(),
        "job_url": job_url.strip(),
        "job_description": job_description,
        "source": "manual input",
        "warning": "",
    }


def get_nested_value(data, *keys, default=""):
    current_value = data
    for key in keys:
        if not isinstance(current_value, dict):
            return default
        current_value = current_value.get(key)

    return current_value or default


def build_application_record(prepared_job, summary, eligibility_result):
    ai_ds_alignment = ""
    visa_risk = ""

    if isinstance(eligibility_result, dict):
        ai_ds_alignment = eligibility_result.get("AI_DS_Alignment", "")
        visa_risk = eligibility_result.get("Risk_Level", "")

    if not ai_ds_alignment:
        ai_ds_alignment = get_nested_value(summary, "ai_data_science_relevance", "level")

    return {
        "company": summary.get("company") or prepared_job["company"],
        "title": summary.get("title") or prepared_job["role"],
        "location": summary.get("location") or prepared_job["location"],
        "url": prepared_job["job_url"],
        "fit_score": summary.get("fit_score", ""),
        "ai_ds_alignment": ai_ds_alignment,
        "visa_risk": visa_risk,
        "recommended_action": summary.get("recommended_action", ""),
        "application_status": "Saved",
        "notes": "",
    }


with analysis_tab:
    company = st.text_input("Company Name")
    role = st.text_input("Job Title")
    location = st.text_input("Location")
    job_url = st.text_input("Job URL")

    job_description = st.text_area("Paste Job Description", height=300)

    if st.button("Analyze Internship"):

        if not job_url.strip() and not job_description.strip():
            st.warning("Please provide a job URL or paste a job description.")
        else:
            with st.spinner("Analyzing..."):
                try:
                    prepared_job = prepare_job_input(company, role, location, job_url, job_description)
                    if prepared_job["warning"]:
                        st.warning(prepared_job["warning"])

                    st.info(f"Using {prepared_job['source']} for this analysis.")

                    job_posting = ingest_job_description(
                        job_description=prepared_job["job_description"],
                        company=prepared_job["company"],
                        title=prepared_job["role"],
                        location=prepared_job["location"],
                        job_url=prepared_job["job_url"],
                    )
                    summary = summarize_job(job_posting)
                    st.write(summary)
                    st.write(job_posting)
                    result = analyze_eligibility(prepared_job["job_description"])

                    display_job_summary(summary)

                    st.subheader("Eligibility Analysis")

                    if isinstance(result, dict):
                        for key, value in result.items():
                            st.markdown(f"**{key.replace('_', ' ')}:** {value}")

                    else:
                        st.write(result)

                    st.session_state["last_analyzed_application"] = build_application_record(
                        prepared_job,
                        summary,
                        result,
                    )

                except (JobIngestionError, JobScraperError, JobSummarizerError) as e:

                    st.error(str(e))

                except Exception as e:

                    st.error("Something went wrong while analyzing the internship.")

                    st.code(traceback.format_exc())

    if "last_analyzed_application" in st.session_state:
        application = st.session_state["last_analyzed_application"]
        if st.button("Save Job"):
            if application_exists(application["url"]):
                st.info("This job is already saved in the applications tracker.")
            elif save_application(**application):
                st.success("Job saved to applications tracker.")
            else:
                st.info("This job is already saved in the applications tracker.")


with tracker_tab:
    st.subheader("Applications Tracker")
    st.dataframe(load_applications(), use_container_width=True)
