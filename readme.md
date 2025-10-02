# 📊 Data Job Market Analysis Dashboard

This project is an end-to-end data platform that automates the collection, transformation, and analysis of data-centric job postings in the French market. It features a modern data stack and an interactive web application built with Streamlit.

The application allows users to explore market trends, identify in-demand skills, and personalize their job search with a custom "match score" to pinpoint the most relevant opportunities.

## ✨ Core Features

* **🤖 Automated Daily Data Pipeline:** A GitHub Actions workflow runs daily to fetch the latest job postings, ensuring the data is always fresh.
* **🎯 Personalized Job Match Score:** Users can define their personal skill set and job preferences to calculate a relevance score for every job offer, sorting them from most to least relevant.
* **📝 Integrated Application Tracking:** A simple Application Tracking System (ATS) allows users to track the status of their applications (`Contacted`, `Refused`, `Positive`) directly within the app, with data persisted in a Supabase database.
* **📈 Interactive Dashboards:** Built with Plotly, the dashboards provide insights into top skills, required technologies (BI tools, cloud platforms), seniority levels, and salary transparency.
* **⚙️ Advanced Filtering & Presets:** Users can filter job offers on numerous criteria and use presets to quickly apply complex search configurations.
* **🔒 Password Protection:** The application includes a password protection feature for private sharing.

## 🛠️ Tech Stack & Architecture

This project is built using a modern, ELT (Extract, Load, Transform) data stack, showcasing best practices in data engineering.

1.  **Scheduler (`GitHub Actions`):** A daily cron job orchestrates the entire data pipeline.
2.  **Extract & Load (`Python`, `SerpApi`, `Supabase`):** A Python script fetches job postings from the Google Jobs API via SerpApi and company data from public APIs. It then loads this raw data into a PostgreSQL database hosted on **Supabase**.
3.  **Transform (`dbt`):** **dbt Core** connects to the Supabase database. It runs a series of SQL models to clean, enrich, join, and test the raw data, materializing a final, analysis-ready table (`analytics_job_offers`).
4.  **Frontend (`Streamlit`):** The interactive web application is built with **Streamlit**. It queries the final dbt model from Supabase and displays the data, handling all user interaction and filtering.

## 📁 Project Structure

The repository is organized as a monorepo containing both the data pipeline and the front-end application.