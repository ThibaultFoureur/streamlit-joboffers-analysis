import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from google import genai
import json
from st_supabase_connection import SupabaseConnection
from datetime import date

st.set_page_config(layout="wide")

# --- Main Application Logic ---
def main():
    conn = st.connection("supabase", type=SupabaseConnection)

    st.sidebar.header("User Account")
    session = conn.auth.get_session()

    # --- Disclaimer and info to the sidebar ---
    st.sidebar.info(
        """
        **About this Project:**
        - For questions, contact [t.foureur@gmail.com](mailto:t.foureur@gmail.com).
        - Explore the code on [GitHub](https://github.com/DEFAULTFoureur/streamlit-joboffers-analysis).
        - Login to save your own search presets or to create a new job search
        """
    )

    if not session:
        # --- Formulaires de Connexion et d'Inscription ---
        with st.sidebar.expander("Login / Sign Up"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")

            col1, col2 = st.columns(2)

            with col1:
                if st.button("Login", use_container_width=True):
                    try:
                        # Tente de connecter l'utilisateur
                        conn.auth.sign_in_with_password({
                            "email": email,
                            "password": password,
                        })
                        st.rerun() # Rafraîchit la page pour montrer l'état connecté
                    except Exception as e:
                        st.error("Invalid login credentials.")

            with col2:
                if st.button("Sign Up", use_container_width=True):
                    try:
                        # Tente d'inscrire un nouvel utilisateur
                        conn.auth.sign_up({
                            "email": email,
                            "password": password,
                        })
                        st.info("Sign up successful! Please check your email to confirm your account.")
                    except Exception as e:
                        st.error(f"Sign up failed: {e}")
    
    else:
        # --- Interface pour l'utilisateur connecté ---
        user_email = session.user.email
        st.sidebar.write("Logged in as:")
        st.sidebar.markdown(f"**{user_email}**")
        
        if st.sidebar.button("Logout"):
            conn.auth.sign_out()
            st.rerun()

    # --- Data Loading (Simplified) ---
    @st.cache_data
    def load_data_from_supabase():
        """Loads the final, clean data from the analytics table."""
        print("Loading data from Supabase...")
        response = conn.client.table("analytics_job_offers").select("*").execute()
        df = pd.DataFrame(response.data)
        if 'found_skills' in df.columns:
            # Ensure it's treated as a dictionary, replacing None with an empty dict
            df['found_skills'] = df['found_skills'].apply(lambda x: x if isinstance(x, dict) else {})
        return df

    # --- Match Score Calculation ---
    def calculate_match_score(row, profile):
        score = 0
        if any(title in row['work_titles_final'] for title in profile.get('target_roles', [])):
            score += 10
        
        if 'found_skills' in row and isinstance(row['found_skills'], dict):
            # 1. Flatten all found skills for the current job into a single set
            all_job_skills = set()
            for category_skills in row['found_skills'].values():
                all_job_skills.update(category_skills)

            # 2. Check if any of the user's preferred skills are in that set
            for skill in profile.get('my_skills', []):
                if skill in all_job_skills:
                    score += 3

        job_info = {row.get('seniority_category'), row.get('consulting_status'), row.get('schedule_type')}
        if profile.get('all_job_info') and not job_info.isdisjoint(profile.get('all_job_info', [])):
                score += 5

        company_info = {row.get('company_category'), row.get('activity_section_details')}
        if profile.get('all_company_info') and not company_info.isdisjoint(profile.get('all_company_info', [])):
            score += 5
            
        min_salary_pref = profile.get('min_salary')
        if min_salary_pref and min_salary_pref > 0:
            if pd.notna(row['annual_min_salary']) and row['annual_min_salary'] >= min_salary_pref:
                score += 10
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
            fig = px.bar(keyword_counts, x=keyword_counts.values, y=keyword_counts.index, orientation='h', title=title,  labels={'x': "Number of offers", 'y': column_name}, text_auto=True)
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

    # --- Helper functions to load presets ---
    @st.cache_data(ttl=10)
    def load_filter_presets(user_id):
        """Fetches all filter presets for a given user."""
        response = conn.client.table("user_filter_presets").select("id, preset_name, filters").eq("user_id", user_id).execute()
        return response.data

    @st.cache_data(ttl=10)
    def load_search_presets(user_id):
        """Fetches all search score presets for a given user."""
        response = conn.client.table("user_search_presets").select("id, preset_name, search_scores").eq("user_id", user_id).execute()
        return response.data
    
    @st.cache_data(ttl=300)
    def load_anonymous_filter_preset():
        """Fetches the default filter preset for anonymous users."""
        anon_id = st.secrets["ANONYMOUS_USER_ID"]
        response = conn.client.table("user_filter_presets").select("filters").eq("user_id", anon_id).maybe_single().execute()
        if response.data:
            return response.data.get("filters")
        return None

    @st.cache_data(ttl=300)
    def load_anonymous_search_preset():
        """Fetches the default search profile for anonymous users."""
        anon_id = st.secrets["ANONYMOUS_USER_ID"]
        response = conn.client.table("user_search_presets").select("search_scores").eq("user_id", anon_id).maybe_single().execute()
        if response.data:
            return response.data.get("search_scores")
        return None
    
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
    if 'active_filter_preset' not in st.session_state: st.session_state.active_filter_preset = None
    if 'active_search_preset' not in st.session_state: st.session_state.active_search_preset = None
    if 'superuser_access' not in st.session_state: st.session_state.superuser_access = False

    # --- Page Navigation ---
    st.sidebar.header("Navigation")
    if st.sidebar.button("Job Offer Breakdown", key="nav_breakdown"):
        st.session_state.page = 'Job Offer Breakdown'
    if st.sidebar.button("Skills Summary", key="nav_skills"):
        st.session_state.page = 'Skills Summary'
    if st.sidebar.button("Raw Data & Matching", key="nav_data"):
        st.session_state.page = 'Raw Data & Matching'
    if session:
        if st.sidebar.button("RESTRICTED - Configure new search", key="nav_superuser"):
            st.session_state.page = 'Superuser'

    # --- Sidebar Filters ---
    st.sidebar.header("Filters")

    # --- Preset Loading and Selection Logic ---
    if session:
        user_id = session.user.id # UPDATED: Get user_id from session
        filter_presets = load_filter_presets(user_id)

        if len(filter_presets) == 1:
            st.sidebar.subheader("Filter Presets")
            preset = filter_presets[0]
            is_toggled = st.sidebar.toggle(f"Activate '{preset['preset_name']}'")
            if is_toggled:
                st.session_state.active_filter_preset = preset['filters']
            else:
                st.session_state.active_filter_preset = None
        
        elif len(filter_presets) > 1:
            st.sidebar.subheader("Filter Presets")
            preset_options = {p['preset_name']: p['filters'] for p in filter_presets}
            preset_names = ["No preset active"] + list(preset_options.keys())
            
            selected_preset_name = st.sidebar.selectbox("Select a saved preset:", options=preset_names)
            
            if selected_preset_name != "No preset active":
                st.session_state.active_filter_preset = preset_options[selected_preset_name]
            else:
                st.session_state.active_filter_preset = None
    else:
        # Logic for anonymous users remains the same
        st.sidebar.subheader("Filter Presets")
        st.sidebar.toggle("Default Active Search", key="preset_active")

    # Definition of default values and presets
    DEFAULTS = {
        'consulting': 'Include All', 'schedule': 'All types', 'seniority_category': [],
        'titles': [], 'category': 'All categories', 'sector': 'All sectors',
        'category_company': [],
    }

    if st.session_state.active_filter_preset:
        # A logged-in user has an active preset
        current_values = st.session_state.active_filter_preset
    elif not session and st.session_state.get('preset_active'):
        # Anonymous user has the default preset toggled
        # Fetch the default preset from the database
        anonymous_preset = load_anonymous_filter_preset()
        # Use the fetched preset if it exists, otherwise fall back to empty defaults
        current_values = anonymous_preset if anonymous_preset else DEFAULTS
    else:
        # No preset is active
        current_values = DEFAULTS

    with st.sidebar.expander("Job Filters"):
        is_consulting_options = ['Include All'] + sorted(source_df['consulting_status'].dropna().unique().tolist())
        default_consulting = current_values['consulting'] if current_values['consulting'] in is_consulting_options else 'Include All'
        selected_is_consulting = st.selectbox('Filter by consulting type:', options=is_consulting_options, index=is_consulting_options.index(default_consulting))

        schedule_type_options = ['All types'] + sorted(source_df['schedule_type'].dropna().unique().tolist())
        selected_schedule_type = st.selectbox(
            'Filter by contract type:', options=schedule_type_options,
            index=schedule_type_options.index(current_values['schedule']) if current_values['schedule'] in schedule_type_options else 0
        )
        
        seniority_options = sorted(source_df['seniority_category'].unique().tolist())
        safe_seniority_defaults = [s for s in current_values['seniority_category'] if s in seniority_options]
        selected_seniority = st.multiselect('Select seniority levels:', options=seniority_options, default=safe_seniority_defaults)

        all_work_titles = sorted(source_df.explode('work_titles_final')['work_titles_final'].dropna().unique().tolist())
        safe_titles_defaults = [t for t in current_values['titles'] if t in all_work_titles]
        selected_work_titles = st.multiselect('Select specific job titles:', options=all_work_titles, default=safe_titles_defaults)
    
    with st.sidebar.expander("Company Filters"):
        category_options = ['All categories'] + sorted(source_df['company_category'].dropna().unique().tolist())
        selected_category_company = st.multiselect(
            "Filter by company category:", options=category_options,
            default=current_values.get('category_company', [])
        )
        selected_sector_company = st.selectbox(
            "Filter by company sector:",
            options=['All sectors'] + sorted(source_df['activity_section_details'].dropna().unique().tolist())
        )
        selected_company = st.selectbox(
            'Filter by company:',
            options=['All companies'] + sorted(source_df['company_name'].dropna().unique().tolist())
        )

    # This section now runs AFTER the variables above have been created.
    if session:
        st.sidebar.subheader("Saving a new Preset")
        preset_name = st.sidebar.text_input("Enter preset name to save")

        if st.sidebar.button("Save Current Filters"):
            if preset_name:
                user_id = session.user.id
                
                current_filters_payload = {
                    "consulting": selected_is_consulting,
                    "schedule": selected_schedule_type,
                    "seniority_category": selected_seniority,
                    "titles": selected_work_titles,
                    "category_company": selected_category_company,
                    "sector": selected_sector_company,
                    "company": selected_company
                }
                
                record = {
                    "user_id": user_id,
                    "preset_name": preset_name,
                    "filters": current_filters_payload
                }
                
                try:
                    conn.client.table("user_filter_presets").insert(record).execute()
                    st.sidebar.success(f"Preset '{preset_name}' saved!")
                except Exception as e:
                    st.sidebar.error(f"Error saving preset: {e}")
            else:
                st.sidebar.warning("Please enter a name for your preset.")

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
        st.header("Most In-Demand Skills")
        
        #1. Aggregate all skills from the 'found_skills' column into a temporary DataFrame
        all_skills_list = []
        for index, row in df_display.iterrows():
            for category, skills in row['found_skills'].items():
                for skill in skills:
                    all_skills_list.append({'category': category.replace('_', ' ').title(), 'skill': skill})
        
        if not all_skills_list:
            st.info("No technical skills were found in the selected job offers.")
        else:
            skills_df = pd.DataFrame(all_skills_list)
            
            # 2. Get a sorted list of unique categories
            unique_categories = sorted(skills_df['category'].unique())

            # 3. Loop through categories and create a plot for each one
            for category in unique_categories:
                category_skills = skills_df[skills_df['category'] == category]
                
                # Use a dummy DataFrame for plotting since plot_value_counts_plotly expects one
                # The function simply counts the values in the specified column
                plot_value_counts_plotly(
                    category_skills,
                    'skill',
                    top_n=10,
                    title=f"Top {category}"
                )
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
        
        with st.expander("Configure my search profile and match score"):
            # --- Search Profile Preset Loading Logic ---
            if session:
                user_id = session.user.id
                search_presets = load_search_presets(user_id)

                if len(search_presets) == 1:
                    preset = search_presets[0]
                    is_toggled = st.toggle(f"Activate '{preset['preset_name']}' profile", key="toggle_search_preset")
                    if is_toggled:
                        st.session_state.active_search_preset = preset['search_scores']
                    else:
                        st.session_state.active_search_preset = None

                elif len(search_presets) > 1:
                    preset_options = {p['preset_name']: p['search_scores'] for p in search_presets}
                    preset_names = ["No preset active"] + list(preset_options.keys())
                    selected_preset_name = st.selectbox("Select a saved profile:", options=preset_names, key="select_search_preset")
                    if selected_preset_name != "No preset active":
                        st.session_state.active_search_preset = preset_options[selected_preset_name]
                    else:
                        st.session_state.active_search_preset = None
            else:
                st.toggle("Activate Default Profile", key="profile_preset_active")

            # --- Logic to Determine Which Profile to Apply ---
            PROFILE_DEFAULTS = { "my_skills": [], "target_roles": [], "all_job_info": [], "all_company_info": [], "min_salary": None }

            if st.session_state.active_search_preset:
                current_profile_values = st.session_state.active_search_preset
            elif not session and st.session_state.get('profile_preset_active'):
                # Anonymous user has the default preset toggled
                # Fetch the default preset from the database
                anonymous_profile = load_anonymous_search_preset()
                # Use the fetched preset if it exists, otherwise fall back to empty defaults
                current_profile_values = anonymous_profile if anonymous_profile else DEFAULTS
            else:
                current_profile_values = PROFILE_DEFAULTS

            combined_skills = set()
            for skills_dict in source_df['found_skills']:
                for skill_list in skills_dict.values():
                    combined_skills.update(skill_list)

            all_skills = sorted(list(combined_skills))
            if "Not specified" in all_skills:
                all_skills.remove("Not specified")

            all_work_titles = sorted(source_df.explode('work_titles_final')['work_titles_final'].dropna().unique().tolist())
            all_job_info_options = sorted(list(set(source_df['seniority_category'].dropna().unique().tolist() + source_df['consulting_status'].dropna().unique().tolist() + source_df['schedule_type'].dropna().unique().tolist())))
            all_company_info_options = sorted(list(set(source_df['company_category'].dropna().unique().tolist() + source_df['activity_section_details'].dropna().unique().tolist())))

            safe_skills = [s for s in current_profile_values.get('my_skills', []) if s in all_skills]
            safe_roles = [r for r in current_profile_values.get('target_roles', []) if r in all_work_titles]
            safe_job_info = [i for i in current_profile_values.get('all_job_info', []) if i in all_job_info_options]
            safe_company_info = [i for i in current_profile_values.get('all_company_info', []) if i in all_company_info_options]
            default_salary = current_profile_values.get("min_salary")

            st.session_state.profile['my_skills'] = st.multiselect('My Skills (+3 pts/skill):', options=all_skills, default=safe_skills)
            st.session_state.profile['target_roles'] = st.multiselect('My Target Roles (+10 pts):', options=all_work_titles, default=safe_roles)
            st.session_state.profile['all_job_info'] = st.multiselect('Job Info (+5 pts):', options=all_job_info_options, default=safe_job_info)
            st.session_state.profile['all_company_info'] = st.multiselect("Company Info (+5 pts):", options=all_company_info_options, default=safe_company_info)
            st.session_state.profile['min_salary'] = st.number_input(
                'Minimum annual salary in € (+5/10 pts):',
                value=default_salary or 0,
                placeholder="Input a minimum salary...",
                min_value=0,
                step=1000,
                format="%d"
            )

            # --- NEW: Save Search Profile button ---
            if session:
                st.markdown("---")
                profile_preset_name = st.text_input("Enter profile name to save")
                if st.button("Save Current Search Profile"):
                    if profile_preset_name:
                        user_id = session.user.id

                        # The profile data is already in st.session_state.profile
                        profile_payload = st.session_state.profile

                        record = {
                            "user_id": user_id,
                            "preset_name": profile_preset_name,
                            "search_scores": profile_payload # Save as JSONB
                        }

                        try:
                            conn.client.table("user_search_presets").insert(record).execute()
                            st.success(f"Profile '{profile_preset_name}' saved!")
                        except Exception as e:
                            st.error(f"Error saving profile: {e}")
                    else:
                        st.warning("Please enter a name for your profile.")
        
        df_display['match_score'] = df_display.apply(lambda row: calculate_match_score(row, st.session_state.profile), axis=1)
        st.write(f"Displaying **{len(df_display)}** filtered offers.")

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

        max_possible_score = 10 + 5 + 5
        max_possible_score += (3 * len(st.session_state.profile.get('my_skills', [])))
        if st.session_state.profile.get('min_salary', 0) > 0:
            max_possible_score += 10
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
            current_user_id = conn.auth.get_session().user.id if conn.auth.get_session() else None
            if current_user_id:
                updated_tracker = st.session_state.df_editor_state[["job_id", "status", "contact_date", "notes"]].copy()
                updated_tracker.dropna(subset=['status'], inplace=True)
                updated_tracker['user_id'] = current_user_id
                if 'contact_date' in updated_tracker.columns:
                    updated_tracker['contact_date'] = pd.to_datetime(updated_tracker['contact_date']).dt.strftime('%Y-%m-%d')
                updated_tracker = updated_tracker.astype(object).where(pd.notnull(updated_tracker), None)
                conn.client.table("tracker").upsert(
                    updated_tracker.to_dict(orient="records"),
                    on_conflict="job_id,user_id"
                ).execute()
                st.success("Your application progress has been saved to Supabase! 🚀")
                st.balloons()
            else:
                st.warning("Please log in to save your progress.")
    
    elif st.session_state.page == 'Superuser':
        st.title("🔒 RESTRICTED - Configure Job Search")

        if st.session_state.superuser_access:
            st.success("Access Granted!")
            user_id = session.user.id

            # --- Initialize session state for the confirmation flow ---
            if 'confirming_new_search' not in st.session_state:
                st.session_state.confirming_new_search = False
            if 'new_config_data' not in st.session_state:
                st.session_state.new_config_data = None

            def process_and_validate_form(user_id, queries, location, skill_config_data):
                """Reads from the UI widgets' state, validates, and saves to Supabase."""
                queries_list = [q.strip() for q in queries.splitlines() if q.strip()]
                
                # Re-parse the text areas back into the nested JSON format
                skills_payload = {}
                for category in skill_config_data:
                    db_category_key = category.lower().replace(" ", "_")
                    skills_payload[db_category_key] = {}
                    # Read the value from the text area's unique key
                    skills_string = st.session_state[f"skill_input_{category}"]
                    
                    skill_groups = [group.strip() for group in skills_string.split('\n') if group.strip()]
                    for group in skill_groups:
                        aliases = [alias.strip() for alias in group.split(',') if alias.strip()]
                        if aliases:
                            canonical_name = aliases[0]
                            skills_payload[db_category_key][canonical_name] = aliases

                if not queries_list or not location.strip():
                    st.error("Job Titles and Location cannot be empty.")
                    return False # Indicate failure

                config_data = {
                    "user_id": user_id,
                    "search_queries": queries_list,
                    "search_location": location.strip(),
                    "search_skills": skills_payload,
                    "updated_at": "now()"
                }
                
                try:
                    conn.client.table("user_configs").upsert(config_data).execute()
                    return True # Indicate success
                except Exception as e:
                    st.error(f"Failed to save configuration: {e}")
                    return False

            def trigger_github_action(run_mode: str, max_pages: str = "5"):
                owner = st.secrets["GITHUB_OWNER"]
                repo = st.secrets["GITHUB_REPO"]
                workflow = st.secrets["WORKFLOW_NAME"]
                token = st.secrets["GITHUB_TOKEN"]

                url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow}/dispatches"
                
                headers = {
                    "Accept": "application/vnd.github.v3+json",
                    "Authorization": f"Bearer {token}",
                }

                data = {
                    "ref": "main", # Or your primary branch name
                    "inputs": {
                        "max_pages": "5",  # The value must be a string
                        "run_mode": run_mode
                    }
                }
                
                response = requests.post(url, headers=headers, json=data)
                
                return response
            
            def add_category_callback():
                # 1. Get the new category name from the text input's state and clean it.
                new_name = st.session_state.get("new_skill_category_name", "").strip()

                if new_name:
                    # 2. Normalize the name to create a database-friendly key.
                    #    (e.g., "My New Category" becomes "my_new_category")
                    db_key = new_name.lower().replace(" ", "_")

                    # 3. Check if this key doesn't already exist in our source of truth.
                    if db_key not in st.session_state.skill_config_data:
                        
                        # 4. THE FIX: Add the new category with an empty dictionary as its value. ✅
                        st.session_state.skill_config_data[db_key] = {}
                    
                    # 5. Clear the text input for the next entry.
                    st.session_state.new_skill_category_name = ""

            def suggest_skills_with_gemini(job_titles: str):
                """Calls the Gemini API to suggest skills based on job titles."""
                try:
                    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

                    # --- The Prompt ---
                    # This prompt is engineered to return a clean JSON object.
                    # It uses your provided example as a guide for the model.
                    prompt = f"""
                    You are an expert technical recruiter helping to configure a job search pipeline for the **French job market**.
                    Based on the following list of job titles, generate a JSON object of relevant hard and soft skills.

                    **CRITICAL INSTRUCTIONS:**
                    1. The final JSON object must have keys for skill categories (e.g., "soft_skills", "administrative_management").
                    2. For each category, the value must be another JSON object.
                    3. In this inner object, the **key must be the skill's name in English** (e.g., "project management").
                    4. The **value must be an array of search terms in both French and English** that correspond to that skill.

                    Here is an example of the desired output format for "Assistante de direction":
                    ```json
                    {{
                    "office_suite": {{
                        "microsoft office": ["microsoft office", "pack office", "office suite"],
                        "excel": ["excel", "tableur"]
                    }},
                    "administrative_management": {{
                        "calendar management": ["calendar management", "gestion d'agenda"],
                        "travel arrangements": ["travel arrangements", "organisation de déplacements"]
                    }},
                    "soft_skills": {{
                        "organization": ["organization", "organisation"],
                        "proactivity": ["proactivity", "proactivité", "prise d'initiative"]
                    }}
                    }}
                    ```

                    Now, generate the JSON for this list of job titles:
                    ---
                    {job_titles}
                    ---
                    """

                    # 2. Call the generate_content method, passing the model and contents
                    response = client.models.generate_content(
                        model="gemini-2.5-flash", # Specify the model here
                        contents=prompt
                    )
                    
                    # 3. Clean and parse the response (this logic remains the same)
                    cleaned_text = response.text.strip().lstrip("```json").rstrip("```")
                    suggested_skills = json.loads(cleaned_text)
                    return suggested_skills

                except json.JSONDecodeError:
                    st.error("The AI returned an invalid format. Please try again.")
                    return None
                except Exception as e:
                    st.error(f"An error occurred while contacting the AI model: {e}")
                    return None

            # --- Initialize session state for skills ---
            if 'skill_config_data' not in st.session_state:
                with st.spinner("Loading existing skill configuration..."):
                    existing_config = conn.client.table("user_configs").select("search_skills").eq("user_id", user_id).single().execute()
                    if existing_config.data and existing_config.data.get("search_skills"):
                        st.session_state.skill_config_data = existing_config.data["search_skills"]
                    else:
                        st.session_state.skill_config_data = {}

            # --- STEP 1: Main Search Parameters (Outside Form) ---
            st.subheader("1. Define Search Parameters")
            existing_config = conn.client.table("user_configs").select("search_queries, search_location").eq("user_id", user_id).execute().data
            default_queries = "\n".join(existing_config[0]['search_queries']) if existing_config else ""
            default_location = existing_config[0]['search_location'] if existing_config else ""

            st.text_area("Job Titles / Keywords (one per line)", value=default_queries, key="queries_input")
            st.text_input("Location (e.g., city, country)", value=default_location, key="location_input")

            # --- STEP 2: Generate or Manually Add Skill Categories (Outside Form) ---
            st.subheader("2. Define Skill Categories")
            
            # AI Suggestion Button
            if st.button("✨ Suggest Skill Categories with AI"):
                if st.session_state.queries_input:
                    with st.spinner("🧠 The AI is thinking..."):
                        suggested_skills = suggest_skills_with_gemini(st.session_state.queries_input)
                        if suggested_skills:
                            # Directly assign the nested JSON to our source of truth
                            st.session_state.skill_config_data = suggested_skills
                            st.success("Skills suggested and populated in the form below!")
                            st.rerun()

            # Manual Category Management
            with st.expander("All skills in raw JSON format"):
                st.write(st.session_state.skill_config_data)
            st.text_input("Or, add a new skill category manually:", key="new_skill_category_name", placeholder="e.g., Certifications")
            st.button("Add Category", on_click=add_category_callback)

            # --- STEP 3: Review and Edit Skills in the Form ---
            with st.form("config_form"):
                st.subheader("3. Review, Edit, and Save")
                
                # Display an input for each skill category
                if not st.session_state.skill_config_data:
                    st.info("No skill categories defined. Add some manually or use the AI suggestion button above.")
                else:
                    # We iterate over a copy of the keys to allow deletion during the loop
                    for category in list(st.session_state.skill_config_data.keys()):
                        # Create columns for the text area and the delete button
                        col1, col2 = st.columns([10, 1])

                        with col1:
                            # Format the nested data from our "source of truth" into the display string
                            skills_object = st.session_state.skill_config_data[category]
                            display_groups = []
                            for english_name, alias_list in skills_object.items():
                                display_groups.append(", ".join(alias_list))
                            display_string = "\n".join(display_groups)

                            # The text area is for editing the formatted string
                            st.text_area(
                                label=f"**{category.replace('_', ' ').title()}** (one skill per line. First value will be used in analysis then aliases separated by `,`)",
                                value=display_string,
                                key=f"skill_input_{category}" # Unique key for reading the edited value later
                            )
                        
                        with col2:
                            st.write("&#8203;") # Small spacer for vertical alignment
                            # The delete button removes the category from our source of truth
                            if st.form_submit_button("❌", key=f"delete_btn_{category}", help=f"Delete '{category}'"):
                                del st.session_state.skill_config_data[category]
                                st.rerun()

                st.markdown("---")
                # --- Conditional Submit Buttons ---
                if not existing_config:
                    submitted_save = st.form_submit_button("Save Configuration")
                else:
                    col1, col2 = st.columns(2)
                    with col1:
                        submitted_update = st.form_submit_button("Update Search", type="secondary")
                    with col2:
                        submitted_new_search = st.form_submit_button("Start New Search (Deletes Old Result)", type="primary")
                        
            # Logic for a brand new configuration save
            if 'submitted_save' in locals() and submitted_save:
                config_data = process_and_validate_form(user_id, st.session_state.queries_input, st.session_state.location_input, st.session_state.skill_config_data)
                if config_data:
                    try:
                        conn.client.table("user_configs").upsert(config_data).execute()
                        st.success("Configuration saved successfully!")
                        st.rerun() # Rerun to show the new button options
                        st.balloons()
                    except Exception as e:
                        st.error(f"Failed to save configuration: {e}")

            # Logic for "Update Only"
            if 'submitted_update' in locals() and submitted_update:
                config_data = process_and_validate_form(user_id, st.session_state.queries_input, st.session_state.location_input, st.session_state.skill_config_data)
                if config_data:
                    try:
                        with st.spinner("Saving configuration and triggering analysis..."):
                            conn.client.table("user_configs").upsert(config_data).execute()
                            api_response = trigger_github_action(run_mode="dbt_only") 
                            if api_response.status_code == 204:
                                st.success("Configuration updated and analysis pipeline (dbt only) started! Indicators should be updated in a few minutes")
                                st.balloons()
                            else:
                                st.error(f"Failed to start pipeline: {api_response.text}")
                    except Exception as e:
                        st.error(f"An error occurred: {e}")

            # Logic for "Start New Search"
            if 'submitted_new_search' in locals() and submitted_new_search:
                config_data = process_and_validate_form(user_id, st.session_state.queries_input, st.session_state.location_input, st.session_state.skill_config_data)
                if config_data:
                    # Store the processed data and set the confirmation flag
                    st.session_state.new_config_data = config_data
                    st.session_state.confirming_new_search = True
                    # Rerun to show the confirmation message
                    st.rerun()

            if st.session_state.confirming_new_search:
                st.warning("⚠️ **ARE YOU SURE?**")
                st.write("This will permanently delete all of your existing job links before starting a completely new search.")
                
                col1, col2 = st.columns(2)
                with col1:
                    # If confirmed, proceed with the destructive actions
                    if st.button("Yes, delete links and start new search", type="primary"):
                        config_data = st.session_state.new_config_data
                        try:
                            with st.spinner("Deleting old job links..."):
                                conn.client.table("raw_job_user_links").delete().eq("user_id", user_id).execute()
                            
                            with st.spinner("Saving new configuration and triggering full pipeline..."):
                                conn.client.table("user_configs").upsert(config_data).execute()
                                api_response = trigger_github_action(run_mode="full_run")
                                
                                if api_response.status_code == 204:
                                    st.success("New search started successfully! Old links have been deleted.")
                                    st.balloons()
                                else:
                                    st.error(f"Failed to start pipeline: {api_response.text}")

                        except Exception as e:
                            st.error(f"An error occurred: {e}")
                        
                        # Reset the confirmation state
                        st.session_state.confirming_new_search = False
                        st.session_state.new_config_data = None
                        # Use st.rerun() to clear the confirmation message
                        st.rerun()

                with col2:
                    # If cancelled, just reset the state
                    if st.button("Cancel"):
                        st.session_state.confirming_new_search = False
                        st.session_state.new_config_data = None
                        st.rerun()

        else:
            password = st.text_input("Enter Superuser Password", type="password")
            if password == st.secrets["PASSWORD"]:
                st.session_state.superuser_access = True
                st.rerun()
            elif password:
                st.error("Incorrect password.")

# --- Run the main function ---
if __name__ == "__main__":
    main()