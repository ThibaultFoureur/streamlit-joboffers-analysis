# 📊 Data Job Market Analysis Dashboard

This project is an end-to-end data platform that automates the collection, transformation, and analysis of data-centric job postings in the French market. It features a modern data stack and an interactive web application built with Streamlit.

The application allows users to explore market trends, identify in-demand skills, and personalize their job search with a custom "match score" to pinpoint the most relevant opportunities.

---

## ✨ Core Features

* **🤖 Dynamic & Configurable Data Pipeline:** A GitHub Actions workflow runs on a schedule to fetch the latest job postings. The entire pipeline is dynamically configured from a superuser panel within the app, allowing an administrator to define new search queries and keywords without touching the code.
* **👤 Multi-User Accounts & Personalization:** Users can log in via Google to save their filter configurations and personalized search profiles. Anonymous users can still explore the public dataset and create temporary presets.
* **🎯 Personalized Job Match Score:** Users can define their personal skill set and job preferences to calculate a relevance score for every job offer, sorting them from most to least relevant.
* **📝 Per-User Application Tracking:** Logged-in users can track the status of their job applications (`Contacted`, `Refused`, `Positive`), with their progress securely saved to their profile in Supabase.
* **📈 Interactive Dashboards:** Built with Plotly, the dashboards provide insights into top skills, required technologies, seniority levels, and salary transparency. The skill analysis is now fully dynamic, based on keyword configurations from all users.
* **🔑 Superuser Admin Panel:** A restricted page, protected by a separate password, allows an administrator to configure and manage the data collection pipeline directly from the application.

---

## 🛠️ Tech Stack & Architecture

This project is built using a modern, ELT (Extract, Load, Transform) data stack, showcasing best practices in data engineering.

1.  **Scheduler (`GitHub Actions`):** A cron job orchestrates the entire data pipeline on a recurring schedule.
2.  **Extract & Load (`Python`, `SerpApi`, `Supabase`):** A Python script is now dynamically driven. It queries a `user_configs` table in Supabase to determine which job titles and locations to search for. It then fetches job postings from the Google Jobs API via SerpApi, enriches company data, and loads the raw data into a PostgreSQL database hosted on **Supabase**. **Supabase Auth** is used for secure Google logins.
3.  **Transform (`dbt`):** **dbt Core** connects to the Supabase database. Its SQL models are now fully dynamic, extracting and categorizing technical skills by cross-referencing job descriptions with the keyword configurations saved by all users. This process cleans, enriches, and tests the data, materializing a final, analysis-ready table.
4.  **Frontend (`Streamlit`):** The interactive web application is built with **Streamlit**. It queries the final dbt model from Supabase and displays the data, handling all user interaction, filtering, and personalized settings.

---

## 📁 Project Structure

The repository is organized as a monorepo containing both the data pipeline and the front-end application.
