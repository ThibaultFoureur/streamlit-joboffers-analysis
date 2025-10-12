import streamlit as st
import pandas as pd
import plotly.express as px
from st_supabase_connection import SupabaseConnection
from datetime import date
from urllib.parse import urlencode
import json
import os
import hashlib
import base64

st.set_page_config(layout="wide")

# --- Main Application Logic ---
def main():
    conn = st.connection("supabase", type=SupabaseConnection)
    query_params = st.query_params

    # Determine the base URL based on the environment ---
    if os.environ.get("APP_ENV") == "production":
        base_url = "https://app-joboffers-analysis.streamlit.app"
    else:
        base_url = "http://lvh.me:8501"

    # --- PKCE: Step 3 - Exchange the code for a session ---
    if "code" in query_params and "pkce_verifier" in query_params:
        auth_code = query_params["code"]
        pkce_verifier = query_params["pkce_verifier"]
        
        try:
            session = conn.auth.exchange_code_for_session({
                "auth_code": auth_code,
                "code_verifier": pkce_verifier,
            })
            # Redirect to the base URL to clear the query parameters
            st.markdown(f'<meta http-equiv="refresh" content="0; url={base_url}">', unsafe_allow_html=True)
            st.stop()
        except Exception as e:
            st.error(f"Error during code exchange: {e}")
            st.stop()

    # --- Disclaimer and info to the sidebar ---
    st.sidebar.info(
        """
        **About this Project:**
        - For questions, contact [t.foureur@gmail.com](mailto:t.foureur@gmail.com).
        - Explore the code on [GitHub](https://github.com/DEFAULTFoureur/streamlit-joboffers-analysis).
        """
    )

    # --- Sidebar for Optional User Login ---
    st.sidebar.header("User Account")
    session = conn.auth.get_session()

    if not session:
        # Clear user info if not logged in
        if 'user' in st.session_state:
            del st.session_state['user']
        if st.sidebar.button("Login with Google", type="primary"):
            
            pkce_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b'=').decode('utf-8')
            pkce_challenge = base64.urlsafe_b64encode(hashlib.sha256(pkce_verifier.encode('utf-8')).digest()).rstrip(b'=').decode('utf-8')

            redirect_url_with_verifier = f"{base_url}?pkce_verifier={pkce_verifier}"

            supabase_url = conn.client.supabase_url
            
            params = {
                "provider": "google",
                "redirect_to": redirect_url_with_verifier,
                "code_challenge": pkce_challenge,
                "code_challenge_method": "S256"
            }
            auth_url = f"{supabase_url}/auth/v1/authorize?{urlencode(params)}"
            
            st.markdown(f'<meta http-equiv="refresh" content="0; url={auth_url}">', unsafe_allow_html=True)
            st.stop()

    else:
        # Store user object in session state
        st.session_state['user'] = session.user 
        
        user_email = st.session_state['user'].email
        st.sidebar.write("Logged in as:")
        st.sidebar.markdown(f"**{user_email}**")
        if st.sidebar.button("Logout"):
            conn.auth.sign_out()
            # Clear the user from session state on logout
            if 'user' in st.session_state:
                del st.session_state['user']
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
    if 'user' in st.session_state:
        if st.sidebar.button("RESTRICTED - Configure new search", key="nav_superuser"):
            st.session_state.page = 'Superuser'

    # --- Sidebar Filters ---
    st.sidebar.header("Filters")

    # --- Preset Loading and Selection Logic ---
    if 'user' in st.session_state:
        user_id = st.session_state['user'].id
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
    PRESET_DEFAULT = {
        'consulting': 'Internal position', 'schedule': 'Full-time', 'seniority_category': ["Senior/Expert", "Not specified"],
        'titles': ["BI/Decision Support Specialist", "Analytics Engineer", "Business/Functional Analyst", "Data Analyst"],
        'category_company': ['Large Enterprise', 'Intermediate-sized Enterprise'], 'sector': 'All sectors', 'company': 'All companies'
    }

    if st.session_state.active_filter_preset:
        # A logged-in user has an active preset
        current_values = st.session_state.active_filter_preset
    elif 'user' not in st.session_state and st.session_state.get('preset_active'):
        # Anonymous user has the default preset toggled
        current_values = PRESET_DEFAULT
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
    if 'user' in st.session_state:
        st.sidebar.subheader("Saving a new Preset")
        preset_name = st.sidebar.text_input("Enter preset name to save")

        if st.sidebar.button("Save Current Filters"):
            if preset_name:
                user_id = st.session_state['user'].id
                
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
            if 'user' in st.session_state:
                user_id = st.session_state['user'].id
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
            PROFILE_DEFAULT = { "my_skills": ["python", "sql", "tableau", "excel", "looker", "gcp", "dbt"], "target_roles": ["Data Analyst", "Analytics Engineer"], "all_job_info": ["Senior/Expert", "Not specified", "Internal position", "Full-time"], "all_company_info": ['Large Enterprise', 'Intermediate-sized Enterprise'], "min_salary": 55000 }

            if st.session_state.active_search_preset:
                current_profile_values = st.session_state.active_search_preset
            elif 'user' not in st.session_state and st.session_state.get('profile_preset_active'):
                current_profile_values = PROFILE_DEFAULT
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
            if 'user' in st.session_state:
                st.markdown("---")
                profile_preset_name = st.text_input("Enter profile name to save")
                if st.button("Save Current Search Profile"):
                    if profile_preset_name:
                        user_id = st.session_state['user'].id

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
            
            user_id = st.session_state['user'].id
            
            # --- NEW: Define the callback function ---
            def add_category_callback():
                # Get the value from the text input's state
                new_name = st.session_state.new_skill_category_name
                if new_name and new_name not in st.session_state.skill_categories:
                    # Add the new category to our skills dictionary
                    st.session_state.skill_categories[new_name] = ""
                    # NOW it's safe to clear the input's state for the next rerun
                    st.session_state.new_skill_category_name = ""

            # Initialize session state for skills if it doesn't exist
            if 'skill_categories' not in st.session_state:
                existing_config = conn.client.table("user_configs").select("search_skills").eq("user_id", user_id).execute().data
                if existing_config and existing_config[0].get("search_skills"):
                    skills_from_db = existing_config[0]["search_skills"]
                    st.session_state.skill_categories = {k: ", ".join(v) for k, v in skills_from_db.items()}
                else:
                    st.session_state.skill_categories = {}

            st.subheader("Skill Keywords")

            # --- UI for MANAGING skill categories (OUTSIDE the form) ---
            st.text_input("New Skill Category Name", key="new_skill_category_name", placeholder="Languages")
            # UPDATED: Use the on_click parameter to call our function
            st.button("Add Category", on_click=add_category_callback)

            # Display delete buttons for existing categories
            for category in list(st.session_state.skill_categories.keys()):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"**{category}**")
                with col2:
                    if st.button(f"❌", key=f"delete_btn_{category}", help=f"Delete '{category}'"):
                        del st.session_state.skill_categories[category]
                        st.rerun()

            # --- The form for ENTERING data ---
            with st.form("config_form"):
                # ... (The rest of your form code remains exactly the same)
                # Fetch existing config for non-skill fields
                existing_config = conn.client.table("user_configs").select("search_queries, search_location").eq("user_id", user_id).execute().data
                default_queries = "\n".join(existing_config[0]['search_queries']) if existing_config else ""
                default_location = existing_config[0]['search_location'] if existing_config else ""

                st.subheader("Search Parameters")
                queries_text = st.text_area("Job Titles / Keywords (comma separated)", value=default_queries, height=150,
                                            placeholder="Analytics Engineer,BI Analyst")
                location_text = st.text_input("One location (e.g., city, country)", value=default_location,
                                              placeholder="Paris")

                st.subheader("Skill Values")
                for category in st.session_state.skill_categories:
                    st.session_state.skill_categories[category] = st.text_area(
                        label=f"{category} (comma-separated)",
                        value=st.session_state.skill_categories[category],
                        key=f"skill_input_{category}",
                        placeholder="English,French,Arabic,Spanish"
                    )
                
                submitted = st.form_submit_button("Save Entire Configuration")

            # --- Handle form submission (remains the same) ---
            if submitted:
                # ... (your existing submission logic)
                pass

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