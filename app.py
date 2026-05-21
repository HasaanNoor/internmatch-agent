import streamlit as st
from src.eligibility_checker import analyze_eligibility

st.title("AI Internship Agent")

company = st.text_input("Company Name")
role = st.text_input("Job Title")
job_url = st.text_input("Job URL")

job_description = st.text_area("Paste Job Description", height=300)

if st.button("Analyze Internship"):

    if not job_description.strip():
        st.warning("Please paste a job description.")
    else:
        with st.spinner("Analyzing..."):
            try:
                result = analyze_eligibility(job_description)

                st.subheader("Eligibility Analysis")

                if isinstance(result, str):
                    st.write(result)
                else:
                    st.json(result)

            except Exception as e:
                st.error("Something went wrong while analyzing the internship.")
                st.code(str(e))