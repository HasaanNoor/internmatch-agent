import streamlit as st
from src.eligibility_checker import analyze_eligibility
from src.job_ingestion import JobIngestionError, ingest_job_description
from src.job_summarizer import JobSummarizerError, summarize_job

st.title("AI Internship Agent")

company = st.text_input("Company Name")
role = st.text_input("Job Title")
location = st.text_input("Location")
job_url = st.text_input("Job URL")

job_description = st.text_area("Paste Job Description", height=300)


def display_items(title, items):
    st.markdown(f"**{title}**")
    if items:
        for item in items:
            st.write(f"- {item}")
    else:
        st.caption("Not found in the posting.")


def display_job_summary(summary):
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

    relevance = summary.get("ai_data_science_relevance", {})
    st.markdown("**AI/Data Science Relevance**")
    st.write(f"Level: {relevance.get('level', 'Unknown')}")
    if relevance.get("reasoning"):
        st.write(relevance["reasoning"])
    if relevance.get("keywords"):
        st.write("Keywords: " + ", ".join(relevance["keywords"]))

    visa = summary.get("visa_related_language", {})
    st.markdown("**Visa / Work Authorization Language**")
    st.write(f"CPT/OPT signal: {visa.get('cpt_opt_signal', 'Unknown')}")
    st.write(f"Sponsorship signal: {visa.get('sponsorship_signal', 'Unknown')}")
    st.write(f"Citizenship or clearance signal: {visa.get('citizenship_or_clearance_signal', 'Unknown')}")
    display_items("Mentions", visa.get("mentions", []))


if st.button("Analyze Internship"):

    if not job_description.strip():
        st.warning("Please paste a job description.")
    else:
        with st.spinner("Analyzing..."):
            try:
                job_posting = ingest_job_description(
                    job_description=job_description,
                    company=company,
                    title=role,
                    location=location,
                    job_url=job_url,
                )
                summary = summarize_job(job_posting)
                result = analyze_eligibility(job_description)

                display_job_summary(summary)

                st.subheader("Eligibility Analysis")

                if isinstance(result, str):
                    st.write(result)
                else:
                    st.json(result)

            except (JobIngestionError, JobSummarizerError) as e:
                st.error(str(e))
            except Exception as e:
                st.error("Something went wrong while analyzing the internship.")
                st.code(str(e))
