from st_supabase_connection import SupabaseConnection
from datetime import date
import json
import os

import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")

# --- LAYER 1: Shared Password Protection (Corrected) ---
def check_password():
    """
    Returns `True` if the user is authenticated.

    Authentication is granted if:
    1. The user has already entered the correct password in the current session.
    2. The user has an active Supabase (Google) session.
    """
    # Check if the password is correct in the session state
    if st.session_state.get("password_correct", False):
        return True

    # NEW: Check for an active Supabase session.
    # This will be True on the redirect back from Google.
    conn = st.connection("supabase", type=SupabaseConnection)
    if conn.auth.get_session():
        st.session_state["password_correct"] = True  # Set the flag for this session
        return True

    # --- If no session exists, show the password entry page ---
    st.title("🔑 Protected Access")
    st.markdown(
        """
        This is a private application. Please enter the password to continue.
        
        - To request access, please contact me at [t.foureur@gmail.com](mailto:t.foureur@gmail.com).
        - For more information about the project, visit the [GitHub repository](https://github.com/ThibaultFoureur/streamlit-joboffers-analysis).
        """
    )
    
    password = st.text_input(
        "Please enter the password...", type="password", key="password_input"
    )

    if password == st.secrets.get("PASSWORD", "default_password"):
        st.session_state["password_correct"] = True
        st.rerun()
    elif password:
        st.error("Incorrect password.")
        
    return False

# --- Main Application Logic ---
# The app will only run if the shared password is correct.
if check_password():

    # Initialize Supabase connection
    conn = st.connection("supabase", type=SupabaseConnection)

    # --- Sidebar for Optional User Login ---
    st.sidebar.header("User Account")
    session = conn.auth.get_session()

    if not session:
        if st.sidebar.button("Login with Google", type="primary"):
            auth_url = conn.auth.sign_in_with_oauth({"provider": "google"})
            st.markdown(f'<meta http-equiv="refresh" content="0; url={auth_url.url}">', unsafe_allow_html=True)
            st.stop()
    else:
        user_email = session.user.email
        st.sidebar.write(f"Logged in as:")
        st.sidebar.markdown(f"**{user_email}**")
        if st.sidebar.button("Logout"):
            conn.auth.sign_out()
            st.rerun()

    # --- Data Loading (Simplified) ---
    @st.cache_data
    def load_data_from_supabase():
        """Loads the final, clean data from the analytics_job_offers dbt model in Supabase."""
        print("Loading data from Supabase...")
        response = conn.client.table("analytics_job_offers").select("*").execute()
        df = pd.DataFrame(response.data)
        # Ensure array columns are treated as lists, handling potential None values
        for col in ['languages', 'bi_tools', 'cloud_platforms', 'data_modelization', 'work_titles_final']:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: x if isinstance(x, list) else [])
        return df

    # --- Match Score Calculation ---
    def calculate_match_score(row, profile):
        score = 0
        # Score for target roles
        if any(title in row['work_titles_final'] for title in profile.get('target_roles', [])):
            score += 10
        
        # Score for skills
        all_job_skills = set(row.get('languages', []) + row.get('bi_tools', []) + row.get('cloud_platforms', []) + row.get('data_modelization', []))
        for skill in profile.get('my_skills', []):
            if skill in all_job_skills:
                score += 3

        # Score for job info (seniority, contract, etc.)
        job_info = {row.get('seniority_category'), row.get('consulting_status'), row.get('schedule_type')}
        if profile.get('all_job_info') and not job_info.isdisjoint(profile.get('all_job_info', [])):
                score += 5

        # Score for company info
        company_info = {row.get('company_category'), row.get('activity_section_details')}
        if profile.get('all_company_info') and not company_info.isdisjoint(profile.get('all_company_info', [])):
            score += 5
            
        # NEW: Score for salary
        min_salary_pref = profile.get('min_salary')
        if min_salary_pref and min_salary_pref > 0:
            # +10 points if the minimum salary meets the preference
            if pd.notna(row['annual_min_salary']) and row['annual_min_salary'] >= min_salary_pref:
                score += 10
            # +5 points if the max salary meets the preference (and min did not)
            elif pd.notna(row['annual_max_salary']) and row['annual_max_salary'] >= min_salary_pref:
                score += 5
                
        return score

    # --- Plotting Functions ---
    def plot_seniorites_pie(df_to_plot):
        seniority_counts = df_to_plot['seniority_category'].value_counts()
        color_map = {'Senior/Expert': '#F6FF47', 'Lead/Manager': '#FF6347', 'Not specified': '#3FD655', 'Intern/Apprentice': "#7A8C8D", 'Junior': "#3FCCD6", 'Other': 'blue'}
        fig = px.pie(values=seniority_counts.values, names=seniority_counts.index, title="Seniority Level Distribution", color=seniority_counts.index, color_discrete_map=color_map)
        st.plotly_chart(fig, use_container_width=True)

    def plot_salary_pie(df_to_plot):
        if df_to_plot['is_salary_mentioned'].dropna().empty:
            st.info("No salary data to display for this selection.")
            return
        salary_counts = df_to_plot['is_salary_mentioned'].value_counts()
        label_map = {True: 'Salary Mentioned', False: 'Salary Not Mentioned'}
        color_map = {True: '#3FD655', False: '#FF6347'}
        fig = px.pie(salary_counts, values=salary_counts.values, names=salary_counts.index.map(label_map), title="Salary Transparency in Job Offers", color=salary_counts.index, color_discrete_map=color_map)
        fig.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig, use_container_width=True)

    def plot_consulting_pie(df_to_plot):
        if df_to_plot['consulting_status'].dropna().empty:
            st.info("No data to display for the consulting distribution with this selection.")
            return
        consulting_counts = df_to_plot['consulting_status'].value_counts()
        label_map = {'Consulting': 'Consulting', 'Probably consulting': 'Probably consulting', 'Internal position': 'Internal position'}
        color_map = {'Consulting': '#FF6347', 'Probably consulting': '#F6FF47', 'Internal position': '#3FD655'}
        fig = px.pie(consulting_counts, values=consulting_counts.values, names=consulting_counts.index.map(label_map), title="Consulting Distribution", color=consulting_counts.index, color_discrete_map=color_map)
        fig.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig, use_container_width=True)
    
    def plot_top_keywords_plotly(df_to_plot, column_name, top_n=10, title=""):
        if column_name not in df_to_plot.columns or df_to_plot[column_name].dropna().empty:
            st.warning(f"No data to display for '{title}'.")
            return
        keywords = df_to_plot.explode(column_name)
        keywords = keywords[keywords[column_name] != "Not specified"]
        keyword_counts = keywords[column_name].value_counts().nlargest(top_n).sort_values()
        if not keyword_counts.empty:
            fig = px.bar(keyword_counts, x=keyword_counts.values, y=keyword_counts.index, orientation='h', title=title)
            st.plotly_chart(fig, use_container_width=True)

    def plot_value_counts_plotly(df_to_plot, column_name, top_n=10, title=""):
        if column_name not in df_to_plot.columns or df_to_plot[column_name].empty:
            st.warning(f"No data to display for '{title}'.")
            return
        series_to_plot = df_to_plot[column_name].fillna('Not specified')
        value_counts = series_to_plot.value_counts().nlargest(top_n).sort_values()
        if not value_counts.empty:
            fig = px.bar(value_counts, x=value_counts.values, y=value_counts.index, orientation='h', title=title, labels={'x': "Number of offers", 'y': column_name.replace('_', ' ').capitalize()}, text_auto=True)
            fig.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info(f"No data found for '{title}' in this selection.")


    # --- Initial Data Load ---
    try:
        source_df = load_data_from_supabase()
    except Exception as e:
        st.error(f"Error loading data from Supabase: {e}")
        st.stop()

    # --- Session State Initialization ---
    if 'page' not in st.session_state: st.session_state.page = 'Job Offer Breakdown'
    if 'preset_active' not in st.session_state: st.session_state.preset_active = False
    if 'profile_preset_active' not in st.session_state: st.session_state.profile_preset_active = False
    if 'profile' not in st.session_state: st.session_state.profile = {}
    if 'last_profile' not in st.session_state: st.session_state.last_profile = {}

    # --- Page Navigation ---
    st.sidebar.header("Navigation")
    if st.sidebar.button("Job Offer Breakdown", key="nav_breakdown"):
        st.session_state.page = 'Job Offer Breakdown'
    if st.sidebar.button("Skills Summary", key="nav_skills"):
        st.session_state.page = 'Skills Summary'
    if st.sidebar.button("Raw Data & Matching", key="nav_data"):
        st.session_state.page = 'Raw Data & Matching'

    # --- Sidebar ---
    st.sidebar.header("Filters")
    st.sidebar.subheader("Filter Presets")
    st.sidebar.toggle("Thibault's Active Search", key="preset_active")

    # Definition of default values and presets
    DEFAULTS = {
        'consulting': 'Include All', 'schedule': 'All types', 'seniority_category': [],
        'titles': [], 'category': 'All categories', 'sector': 'All sectors',
        'category_company': [],
    }
    PRESET_THIBAULT = {
        'consulting': 'Internal position', 'schedule': 'Full-time', 'seniority_category': ["Senior/Expert", "Not specified"],
        'titles': ["BI/Decision Support Specialist", "Analytics Engineer", "Business/Functional Analyst", "Data Analyst"],
        'category_company': ['Large Enterprise', 'Intermediate-sized Enterprise'], 'sector': 'All sectors', 'company': 'All companies'
    }

    current_values = PRESET_THIBAULT if st.session_state.preset_active else DEFAULTS

    # --- DISPLAY FILTERS ---
    st.sidebar.subheader("Job Filters")

    is_consulting_options = ['Include All'] + sorted(source_df['consulting_status'].dropna().unique().tolist())
    default_consulting = current_values['consulting'] if current_values['consulting'] in is_consulting_options else 'Include All'
    selected_is_consulting = st.sidebar.selectbox('Filter by consulting type:', options=is_consulting_options, index=is_consulting_options.index(default_consulting))

    schedule_type_options = ['All types'] + sorted(source_df['schedule_type'].dropna().unique().tolist())
    selected_schedule_type = st.sidebar.selectbox(
        'Filter by contract type:', options=schedule_type_options,
        index=schedule_type_options.index(current_values['schedule']) if current_values['schedule'] in schedule_type_options else 0
    )
    
    seniority_options = sorted(source_df['seniority_category'].unique().tolist())
    safe_seniority_defaults = [s for s in current_values['seniority_category'] if s in seniority_options]
    selected_seniority = st.sidebar.multiselect('Select seniority levels:', options=seniority_options, default=safe_seniority_defaults)

    all_work_titles = sorted(source_df.explode('work_titles_final')['work_titles_final'].dropna().unique().tolist())
    safe_titles_defaults = [t for t in current_values['titles'] if t in all_work_titles]
    selected_work_titles = st.sidebar.multiselect('Select specific job titles:', options=all_work_titles, default=safe_titles_defaults)
    
    st.sidebar.subheader("Company Filters")
    category_options = ['All categories'] + sorted(source_df['company_category'].dropna().unique().tolist())
    selected_category_company = st.sidebar.multiselect(
        "Filter by company category:", options=category_options,
        default=current_values['category_company']
    )
    selected_sector_company = st.sidebar.selectbox(
        "Filter by company sector:",
        options=['All sectors'] + sorted(source_df['activity_section_details'].dropna().unique().tolist())
    )
    selected_company = st.sidebar.selectbox(
        'Filter by company:',
        options=['All companies'] + sorted(source_df['company_name'].dropna().unique().tolist())
    )
    
    # --- Filter Application ---
    df_display = source_df.copy()
    if selected_is_consulting != 'Include All':
        df_display = df_display[df_display['consulting_status'] == selected_is_consulting]
    if selected_sector_company != 'All sectors':
        df_display = df_display[df_display['activity_section_details'] == selected_sector_company]
    if selected_category_company:
        df_display = df_display[df_display['company_category'].isin(selected_category_company)]
    if selected_company != 'All companies':
        df_display = df_display[df_display['company_name'] == selected_company]
    if selected_schedule_type != 'All types':
        df_display = df_display[df_display['schedule_type'] == selected_schedule_type]
    if selected_seniority:
        df_display = df_display[df_display['seniority_category'].isin(selected_seniority)]
    if selected_work_titles:
        df_display = df_display[df_display['work_titles_final'].apply(
            lambda titles_in_row: any(title in titles_in_row for title in selected_work_titles)
        )]

    # --- Page Display ---
    if st.session_state.page == 'Skills Summary':
        st.title("📊 Market Skills Summary")
        st.write(f"Analysis of **{len(df_display)}** filtered job offers.")
        st.header("Most In-Demand Technical Skills")
        plot_top_keywords_plotly(df_display, 'bi_tools', title="Top BI Tools / Technical Solutions")
        st.markdown("---") 
        plot_top_keywords_plotly(df_display, 'languages', title="Top Technical Languages")
        st.markdown("---") 
        plot_top_keywords_plotly(df_display, 'cloud_platforms', title="Top Cloud & Data Platforms")
        st.markdown("---") 
    elif st.session_state.page == 'Job Offer Breakdown':
        st.title("📄 Job Offer Breakdown")
        st.write(f"Analysis of **{len(df_display)}** filtered job offers.")
        col1, col2 = st.columns(2)
        with col1:
            st.header("Job Titles")
            plot_top_keywords_plotly(df_display, 'work_titles_final', top_n=15, title="Top Job Titles")
        with col2:
            st.header("Seniority Levels")
            plot_seniorites_pie(df_display)
        st.markdown("---") 
        col1, col2 = st.columns(2)
        with col1:
            st.header("Contract Type")
            plot_value_counts_plotly(df_display, 'schedule_type', top_n=15, title="Top Contract Types")
        with col2:
            st.header("Consulting")
            plot_consulting_pie(df_display)
        st.markdown("---") 
        col1, col2 = st.columns(2)
        with col1:
            st.header("Top Company Categories")
            plot_value_counts_plotly(df_display, 'company_category', top_n=15, title="Top Categories")
        with col2:
            st.header("Salaries")
            plot_salary_pie(df_display)
        st.markdown("---") 
        col1, col2 = st.columns(2)
        with col1:
            st.header("Company Analysis")
            plot_value_counts_plotly(df_display, 'company_name', top_n=15, title="Top Companies")
        with col2:
            st.header("Top Activities")
            plot_value_counts_plotly(df_display, 'activity_section_details', top_n=15, title="Top Activities")
        st.markdown("---") 

    elif st.session_state.page == 'Raw Data & Matching':
        st.title(" Explorer Offers by Relevance")
        
        # --- PROFILE & MATCH SCORE SECTION (IN AN EXPANDER) ---
        with st.expander("Configure my search profile and match score"):
            st.toggle("Activate Thibault's Profile", key="profile_preset_active")

            PROFILE_DEFAULTS = {
                "my_skills": [], "target_roles": [], "all_job_info": [],
                "all_company_info": [], "min_salary": None
            }
            PROFILE_THIBAULT = {
                "my_skills": ["python", "sql", "tableau","excel","looker","gcp","dbt"],
                "target_roles": ["Data Analyst", "Analytics Engineer"],
                "all_job_info": ["Senior/Expert", "Not specified", "Internal position", "Full-time"],
                "all_company_info": ['Large Enterprise', 'Intermediate-sized Enterprise'],
                "min_salary": 55000
            }
            current_profile_values = PROFILE_THIBAULT if st.session_state.profile_preset_active else PROFILE_DEFAULTS

            # Explode and combine all skill lists, dropping nulls immediately
            combined_skills = (
                source_df.explode('languages')['languages'].dropna().tolist() +
                source_df.explode('bi_tools')['bi_tools'].dropna().tolist() +
                source_df.explode('cloud_platforms')['cloud_platforms'].dropna().tolist() +
                source_df.explode('data_modelization')['data_modelization'].dropna().tolist()
            )
            all_skills = sorted(list(set(combined_skills)))

            if "Not specified" in all_skills: 
                all_skills.remove("Not specified")

            # Prepare options lists
            all_work_titles = sorted(source_df.explode('work_titles_final')['work_titles_final'].dropna().unique().tolist())
            all_job_info_options = sorted(list(set(source_df['seniority_category'].dropna().unique().tolist() + source_df['consulting_status'].dropna().unique().tolist() + source_df['schedule_type'].dropna().unique().tolist())))
            all_company_info_options = sorted(list(set(source_df['company_category'].dropna().unique().tolist() + source_df['activity_section_details'].dropna().unique().tolist())))

            # Create safe defaults by filtering presets against available options
            safe_skills = [s for s in current_profile_values.get('my_skills', []) if s in all_skills]
            safe_roles = [r for r in current_profile_values.get('target_roles', []) if r in all_work_titles]
            safe_job_info = [i for i in current_profile_values.get('all_job_info', []) if i in all_job_info_options]
            safe_company_info = [i for i in current_profile_values.get('all_company_info', []) if i in all_company_info_options]
            default_salary = current_profile_values.get("min_salary")

            # Use the safe defaults in the widgets
            st.session_state.profile['my_skills'] = st.multiselect('My Skills (+3 pts/skill):', options=all_skills, default=safe_skills)
            st.session_state.profile['target_roles'] = st.multiselect('My Target Roles (+10 pts):', options=all_work_titles, default=safe_roles)
            st.session_state.profile['all_job_info'] = st.multiselect('Job Info (+5 pts):', options=all_job_info_options, default=safe_job_info)
            st.session_state.profile['all_company_info'] = st.multiselect("Company Info (+5 pts):", options=all_company_info_options, default=safe_company_info)
            
            # NEW: Number input for minimum salary
            st.session_state.profile['min_salary'] = st.number_input(
                'Minimum annual salary in € (+5/10 pts):',
                value=default_salary or 0,
                placeholder="Input a minimum salary...",
                min_value=0,
                step=1000,
                format="%d"
            )
        
        # Recalculate scores and display data
        df_display['match_score'] = df_display.apply(lambda row: calculate_match_score(row, st.session_state.profile), axis=1)
        st.write(f"Displaying **{len(df_display)}** filtered offers.")

        # --- Data editor logic ---
        conn = st.connection("supabase", type=SupabaseConnection)
        response = conn.client.table("tracker").select("*").execute()
        tracker_df = pd.DataFrame(response.data)
        if tracker_df.empty:
            tracker_df = pd.DataFrame(columns=['job_id', 'status', 'contact_date', 'notes'])
        if 'contact_date' in tracker_df.columns:
            tracker_df['contact_date'] = pd.to_datetime(tracker_df['contact_date']).dt.date

        df_display_sorted = df_display.sort_values(by="match_score", ascending=False)
        df_with_status = pd.merge(df_display_sorted, tracker_df, on="job_id", how="left")
        df_prepared = df_with_status.copy()

        if 'status' not in df_prepared.columns: df_prepared['status'] = None
        if 'contact_date' not in df_prepared.columns: df_prepared['contact_date'] = None
        if 'notes' not in df_prepared.columns: df_prepared['notes'] = None
        
        desired_order = ['match_score', 'title', 'company_name', 'status', 'contact_date', 'annual_min_salary', 'annual_max_salary']
        other_columns = [col for col in df_prepared.columns if col not in desired_order]
        df_prepared = df_prepared[desired_order + other_columns]

        # --- SESSION STATE UPDATE LOGIC ---
        profile_has_changed = st.session_state.get('profile') != st.session_state.get('last_profile')

        try:
            current_ids_in_state = set(st.session_state.df_editor_state['job_id'])
        except (KeyError, AttributeError):
            current_ids_in_state = set()
        newly_filtered_ids = set(df_prepared['job_id'])
        filters_have_changed = current_ids_in_state != newly_filtered_ids

        if 'df_editor_state' not in st.session_state or filters_have_changed or profile_has_changed:
            st.session_state.df_editor_state = df_prepared.copy()
            st.session_state.last_profile = st.session_state.profile.copy()

        # Dynamically calculate the maximum possible score based on the current profile
        max_possible_score = 10 + 5 + 5 # Base score for role, job info, company info
        max_possible_score += (3 * len(st.session_state.profile.get('my_skills', [])))
        if st.session_state.profile.get('min_salary', 0) > 0:
            max_possible_score += 10 # Max points from salary
            
        if max_possible_score == 0: max_possible_score = 1

        edited_df = st.data_editor(
            st.session_state.df_editor_state,
            column_config={
                "match_score": st.column_config.ProgressColumn(
                    "Score", help="Relevance score based on your profile",
                    min_value=0, max_value=max_possible_score, width="small"
                ),
                "title": st.column_config.Column(pinned=True, width="medium"),
                "company_name": st.column_config.Column(pinned=True, width="small"),
                "status": st.column_config.SelectboxColumn(
                    "Status", width="small", options=["Contacted", "Refused", "Positive"],
                    required=False, pinned=True,
                ),
                "contact_date": st.column_config.DateColumn("Contact Date", width="small"),
                "annual_min_salary": st.column_config.NumberColumn("Min Salary (€)", format="€%d"),
                "annual_max_salary": st.column_config.NumberColumn("Max Salary (€)", format="€%d"),
                "apply_link_1": st.column_config.LinkColumn("Apply Link 1"),
                "job_id": None
            },
            hide_index=True, use_container_width=True, key="job_editor"
        )

        if not edited_df.equals(st.session_state.df_editor_state):
            df_updates = edited_df.copy()
            for index, row in df_updates.iterrows():
                if index in st.session_state.df_editor_state.index:
                    original_row = st.session_state.df_editor_state.loc[index]
                    original_status = original_row['status'] if pd.notna(original_row['status']) else ""
                    current_status = row['status'] if pd.notna(row['status']) else ""
                    if current_status == 'Contacted' and original_status != 'Contacted':
                        df_updates.loc[index, 'contact_date'] = date.today()
            st.session_state.df_editor_state = df_updates.copy()
            st.rerun()

        if st.button("Save My Progress to Supabase"):
            # Récupérer l'ID de l'utilisateur de la session actuelle
            # Cela fonctionne que l'utilisateur soit connecté avec Google ou anonyme
            current_user_id = conn.auth.get_session().user.id if conn.auth.get_session() else None

            if current_user_id:
                # Préparer les données pour la sauvegarde
                updated_tracker = st.session_state.df_editor_state[["job_id", "status", "contact_date", "notes"]].copy()
                updated_tracker.dropna(subset=['status'], inplace=True)
                
                # Ajouter l'ID de l'utilisateur à chaque ligne
                updated_tracker['user_id'] = current_user_id

                if 'contact_date' in updated_tracker.columns:
                    updated_tracker['contact_date'] = pd.to_datetime(updated_tracker['contact_date']).dt.strftime('%Y-%m-%d')
                
                updated_tracker = updated_tracker.astype(object).where(pd.notnull(updated_tracker), None)
                
                # 'upsert' mettra à jour les entrées existantes ou en créera de nouvelles
                # Il doit savoir sur quelle(s) colonne(s) se baser pour détecter un conflit (une ligne existante)
                conn.client.table("tracker").upsert(
                    updated_tracker.to_dict(orient="records"),
                    on_conflict="job_id,user_id" # Conflit si une ligne existe déjà pour ce job ET cet utilisateur
                ).execute()
                
                st.success("Your application progress has been saved to Supabase! 🚀")
                st.balloons()
            else:
                st.error("Could not identify user. Please try logging in again.")