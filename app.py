from st_supabase_connection import SupabaseConnection
from datetime import date
import json
import os

import streamlit as st
import pandas as pd
import plotly.express as px
import ast

st.set_page_config(layout="wide")

# --- Protection par mot de passe ---
def check_password():
    if "password_correct" in st.session_state and st.session_state["password_correct"]:
        return True

    st.header("🔑 Accès Protégé")
    password = st.text_input("Veuillez entrer le mot de passe pour accéder au dashboard.", type="password")

    if password == st.secrets.get("PASSWORD", "default_password"):
        st.session_state["password_correct"] = True
        st.rerun()
        return True
    elif password:
        st.error("Mot de passe incorrect.")
    
    return False

# --- Lancement de l'application ---
if check_password():
    # --- Fonctions de préparation et de plotting ---

    def categorize_seniority(seniority_list):
        if 'Non renseigné' in seniority_list: return "Non renseigné"
        if 'Stagiaire/Alternant' in seniority_list: return "Stagiaire/Alternant"
        if 'Senior/Expert' in seniority_list: return "Senior/Expert"
        if 'Lead/Manager' in seniority_list: return "Lead/Manager"
        if 'Junior' in seniority_list: return "Junior"
        return "Autre"

    @st.cache_data
    def load_and_prepare_data(path):
        df = pd.read_csv(path)
        skill_columns = ['outils_bi', 'langages', 'cloud', 'modelisation', 'work_titles', 'type_contrat', 'seniorites']
        
        def convert_string_to_list(val):
            if pd.isna(val) or not isinstance(val, str) or not val.startswith('['):
                return ["Non renseigné"]
            try:
                result = ast.literal_eval(val)
                return result if result else ["Non renseigné"]
            except:
                return ["Non renseigné"]

        for col in skill_columns:
            if col in df.columns:
                df[col] = df[col].apply(convert_string_to_list)
        
        df['salaire_present'] = df['salary'].notna()
        df['seniority_category'] = df['seniorites'].apply(categorize_seniority)
        
        return df

    # --- FONCTION DE SCORING MISE À JOUR ---
    def calculate_match_score(row, profile):
        score = 0
        
        # +10 points for a matching job title
        if any(title in row['work_titles'] for title in profile['target_roles']):
            score += 10
        
        # +3 for each matching skill
        all_job_skills = set(row['langages'] + row['outils_bi'] + row['cloud'] + row['modelisation'])
        for skill in profile['my_skills']:
            if skill in all_job_skills:
                score += 3

        # +5 for matching job info (seniority, consulting, schedule)
        job_info = {row['seniority_category'], row['is_consulting_final'], row['schedule_type']}
        if profile['all_job_info'] and not job_info.isdisjoint(profile['all_job_info']):
             score += 5

        # +5 for matching company info (category, sector)
        company_info = {row['categorie_entreprise'], row['section_activite_principale_detail']}
        if profile['all_company_info'] and not company_info.isdisjoint(profile['all_company_info']):
            score += 5
            
        return score

    # ... (les autres fonctions de plotting restent identiques) ...
    def plot_seniorites_pie(df_to_plot):
        seniority_counts = df_to_plot['seniority_category'].value_counts()
        color_map = {'Senior/Expert': '#F6FF47', 'Lead/Manager': '#FF6347', 'Non renseigné': '#3FD655', 'Stagiaire/Alternant': "#7A8C8D", 'Junior': "#3FCCD6", 'Autre': 'blue'}
        fig = px.pie(values=seniority_counts.values, names=seniority_counts.index, title="Répartition des niveaux de séniorité", color=seniority_counts.index, color_discrete_map=color_map)
        st.plotly_chart(fig, use_container_width=True)

    def plot_salary_pie(df_to_plot):
        if df_to_plot['salaire_present'].dropna().empty:
            st.info("Aucune donnée de salaire à afficher pour cette sélection.")
            return
        salary_counts = df_to_plot['salaire_present'].value_counts()
        label_map = {True: 'Salaire Mentionné', False: 'Salaire Non Mentionné'}
        color_map = {True: '#3FD655', False: '#FF6347'}
        fig = px.pie(salary_counts, values=salary_counts.values, names=salary_counts.index.map(label_map), title="Transparence des salaires dans les offres", color=salary_counts.index, color_discrete_map=color_map)
        fig.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig, use_container_width=True)

    def plot_consulting_pie(df_to_plot):
        if df_to_plot['is_consulting_final'].dropna().empty:
            st.info("Aucune donnée à afficher pour la répartition du consulting avec cette sélection.")
            return
        consulting_counts = df_to_plot['is_consulting_final'].value_counts()
        label_map = {'Consulting': 'Consulting', 'Probablement consulting': 'Probablement consulting', 'Poste interne': 'Poste interne'}
        color_map = {'Consulting': '#FF6347', 'Probablement consulting': '#F6FF47', 'Poste interne': '#3FD655'}
        fig = px.pie(consulting_counts, values=consulting_counts.values, names=consulting_counts.index.map(label_map), title="Répartition du consulting", color=consulting_counts.index, color_discrete_map=color_map)
        fig.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig, use_container_width=True)
    
    def plot_top_keywords_plotly(df_to_plot, column_name, top_n=10, title=""):
        if column_name not in df_to_plot.columns or df_to_plot[column_name].dropna().empty:
            st.warning(f"Pas de données à afficher pour '{title}'.")
            return
        keywords = df_to_plot.explode(column_name)
        keyword_counts = keywords[column_name].value_counts().nlargest(top_n).sort_values()
        if not keyword_counts.empty:
            fig = px.bar(
                keyword_counts, x=keyword_counts.values, y=keyword_counts.index,
                orientation='h', title=title,
                labels={'x': "Nombre d'offres", 'y': column_name.replace('_', ' ').capitalize()}, text_auto=True
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info(f"Aucune compétence trouvée pour '{title}' dans cette sélection.")

    def plot_value_counts_plotly(df_to_plot, column_name, top_n=10, title=""):
        if column_name not in df_to_plot.columns or df_to_plot[column_name].empty:
            st.warning(f"Pas de données à afficher pour '{title}'.")
            return
        series_to_plot = df_to_plot[column_name].fillna('Non spécifié')
        value_counts = series_to_plot.value_counts().nlargest(top_n).sort_values()
        if not value_counts.empty:
            fig = px.bar(value_counts, x=value_counts.values, y=value_counts.index, orientation='h', title=title, labels={'x': "Nombre d'offres", 'y': column_name.replace('_', ' ').capitalize()}, text_auto=True)
            fig.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info(f"Aucune donnée trouvée pour '{title}' dans cette sélection.")


    # --- Chargement initial des données ---
    try:
        source_df = load_and_prepare_data('offres_emploi_data_enriched_with_company_info.csv')
    except FileNotFoundError:
        st.error("ERREUR : Fichier 'offres_emploi_data_enriched_with_company_info.csv' introuvable.")
        st.stop()

    # --- Initialisation de l'état de session ---
    if 'page' not in st.session_state:
        st.session_state.page = 'Décomposition des offres'
    if 'preset_active' not in st.session_state:
        st.session_state.preset_active = False
    if 'profile_preset_active' not in st.session_state:
        st.session_state.profile_preset_active = False


    # --- Navigation entre les pages ---
    st.sidebar.header("Navigation")
    if st.sidebar.button("Décomposition des offres", key="nav_decomposition"):
        st.session_state.page = 'Décomposition des offres'
    if st.sidebar.button("Synthèse des compétences", key="nav_competences"):
        st.session_state.page = 'Synthèse des compétences'
    if st.sidebar.button("Données brutes", key="nav_donnees"):
        st.session_state.page = 'Données brutes'

    # --- Barre latérale (Sidebar) ---
    st.sidebar.header("Filtres")
    st.sidebar.subheader("Presets de filtres")
    st.sidebar.toggle("Recherche active de Thibault", key="preset_active")

    # Définition des valeurs par défaut et des presets
    DEFAULTS = {
        'consulting': 'Inclure tout', 'schedule': 'Tous les types', 'seniority_category': [],
        'titles': [], 'category': 'Toutes les catégories', 'sector': 'Tous les secteurs',
        'category_company': [],
    }
    PRESET_THIBAULT = {
        'consulting': 'Poste interne', 'schedule': 'À plein temps', 'seniority_category': ["Senior/Expert", "Non renseigné"],
        'titles': ["Spécialiste BI/Décisionnel", "Analytics Engineer", "Business/Functional Analyst", "Data Analyst"],
        'category_company': ['GE','PME'], 'sector': 'Tous les secteurs', 'company': 'Toutes les entreprises'
    }

    current_values = PRESET_THIBAULT if st.session_state.preset_active else DEFAULTS

    # --- AFFICHAGE DES FILTRES ---
    st.sidebar.subheader("Filtres sur le poste")
    is_consulting_options = ['Inclure tout'] + sorted(source_df['is_consulting_final'].dropna().unique().tolist())
    selected_is_consulting = st.sidebar.selectbox(
        'Filtrer par mention de consulting :', options=is_consulting_options,
        index=is_consulting_options.index(current_values['consulting'])
    )
    schedule_type_options = ['Tous les types'] + sorted(source_df['schedule_type'].dropna().unique().tolist())
    selected_schedule_type = st.sidebar.selectbox(
        'Filtrer par type de contrat :', options=schedule_type_options,
        index=schedule_type_options.index(current_values['schedule'])
    )
    seniority_options = sorted(source_df['seniority_category'].unique().tolist())
    selected_seniority = st.sidebar.multiselect(
        'Choisir des niveaux de séniorité :', options=seniority_options,
        default=current_values['seniority_category']
    )
    all_work_titles = sorted(source_df.explode('work_titles')['work_titles'].dropna().unique().tolist())
    if "Non renseigné" in all_work_titles: all_work_titles.remove("Non renseigné")
    selected_work_titles = st.sidebar.multiselect(
        'Choisir des intitulés spécifiques :', options=all_work_titles,
        default=current_values['titles']
    )
    
    st.sidebar.subheader("Filtres sur la société")
    category_options = ['Toutes les catégories'] + sorted(source_df['categorie_entreprise'].dropna().unique().tolist())
    selected_category_company = st.sidebar.multiselect(
        "Filtrer par catégorie d'entreprise :", options=category_options,
        default=current_values['category_company']
    )
    selected_sector_company = st.sidebar.selectbox(
        "Filtrer par secteur d'entreprise :",
        options=['Tous les secteurs'] + sorted(source_df['section_activite_principale_detail'].dropna().unique().tolist())
    )
    selected_company = st.sidebar.selectbox(
        'Filtrer par entreprise :',
        options=['Toutes les entreprises'] + sorted(source_df['company_name'].dropna().unique().tolist())
    )
    
    # --- Application des filtres ---
    df_display = source_df.copy()
    if selected_is_consulting != 'Inclure tout':
        df_display = df_display[df_display['is_consulting_final'] == selected_is_consulting]
    if selected_sector_company != 'Tous les secteurs':
        df_display = df_display[df_display['section_activite_principale_detail'] == selected_sector_company]
    if selected_category_company:
        df_display = df_display[df_display['categorie_entreprise'].isin(selected_category_company)]
    if selected_company != 'Toutes les entreprises':
        df_display = df_display[df_display['company_name'] == selected_company]
    if selected_schedule_type != 'Tous les types':
        df_display = df_display[df_display['schedule_type'] == selected_schedule_type]
    if selected_seniority:
        df_display = df_display[df_display['seniority_category'].isin(selected_seniority)]
    if selected_work_titles:
        df_display = df_display[df_display['work_titles'].apply(
            lambda titles_in_row: any(title in titles_in_row for title in selected_work_titles)
        )]
        
    # --- Initialisation du profil de l'utilisateur (sera utilisé plus tard) ---
    if 'profile' not in st.session_state:
        st.session_state.profile = {}

    # --- Affichage des pages ---
    if st.session_state.page == 'Synthèse des compétences':
        st.title("📊 Synthèse des compétences du marché")
        st.write(f"Analyse de **{len(df_display)}** offres d'emploi filtrées.")
        st.header("Compétences techniques les plus demandées")
        plot_top_keywords_plotly(df_display, 'outils_bi', title="Top Outils BI / Solutions Techniques")
        st.markdown("---") 
        plot_top_keywords_plotly(df_display, 'langages', title="Top Langages Techniques")
        st.markdown("---") 
        plot_top_keywords_plotly(df_display, 'cloud', title="Top Plateformes Cloud & Data")
        st.markdown("---") 
    elif st.session_state.page == 'Décomposition des offres':
        st.title("📄 Décomposition des offres")
        st.write(f"Analyse de **{len(df_display)}** offres d'emploi filtrées.")
        col1, col2 = st.columns(2)
        with col1:
            st.header("Intitulés de poste")
            plot_top_keywords_plotly(df_display, 'work_titles', top_n=15, title="Top des intitulés de poste")
        with col2:
            st.header("Seniorités")
            plot_seniorites_pie(df_display)
        st.markdown("---") 
        col1, col2 = st.columns(2)
        with col1:
            st.header("Type de contrat")
            plot_value_counts_plotly(df_display, 'schedule_type', top_n=15, title="Top des types de contrats")
        with col2:
            st.header("Consulting")
            plot_consulting_pie(df_display)
        st.markdown("---") 
        col1, col2 = st.columns(2)
        with col1:
            st.header("Top categorie d'entreprise")
            plot_value_counts_plotly(df_display, 'categorie_entreprise', top_n=15, title="Top des catégorie")
        with col2:
            st.header("Salaires")
            plot_salary_pie(df_display)
        st.markdown("---") 
        col1, col2 = st.columns(2)
        with col1:
            st.header("Analyse des entreprises")
            plot_value_counts_plotly(df_display, 'company_name', top_n=15, title="Top entreprises")
        with col2:
            st.header("Top activite")
            plot_value_counts_plotly(df_display, 'section_activite_principale_detail', top_n=15, title="Top des activités")
        st.markdown("---") 

    elif st.session_state.page == 'Données brutes':
        st.title(" Explorer les offres par pertinence")
        
        # --- SECTION PROFIL & MATCH SCORE (DANS UN EXPANDER) ---
        with st.expander("Configurer mon profil de recherche et le match score"):
            st.toggle("Activer le profil de Thibault", key="profile_preset_active")

            PROFILE_DEFAULTS = {
                "my_skills": [], "target_roles": [], "all_job_info": [], "all_company_info": []
            }
            PROFILE_THIBAULT = {
                "my_skills": ["python", "sql", "tableau","excel","looker","metabase","vba","gcp","bigquery","airflow","dbt"],
                "target_roles": ["Data Analyst", "Analytics Engineer"],
                "all_job_info": ["Senior/Expert", "Non renseigné", "Poste interne", "À plein temps"],
                "all_company_info": ['GE', 'PME']
            }
            
            current_profile_values = PROFILE_THIBAULT if st.session_state.profile_preset_active else PROFILE_DEFAULTS

            # Préparation des listes d'options pour les multiselects
            all_skills = sorted(list(set(
                source_df.explode('langages')['langages'].dropna().unique().tolist() +
                source_df.explode('outils_bi')['outils_bi'].dropna().unique().tolist() +
                source_df.explode('cloud')['cloud'].dropna().unique().tolist() +
                source_df.explode('modelisation')['modelisation'].dropna().unique().tolist()
            )))
            if "Non renseigné" in all_skills: all_skills.remove("Non renseigné")

            all_job_info_options = sorted(list(set(
                source_df['seniority_category'].dropna().unique().tolist() +
                source_df['is_consulting_final'].dropna().unique().tolist() +
                source_df['schedule_type'].dropna().unique().tolist()
            )))
            all_company_info_options = sorted(list(set(
                source_df['categorie_entreprise'].dropna().unique().tolist() +
                source_df['section_activite_principale_detail'].dropna().unique().tolist()
            )))
            
            # Widgets pour éditer le profil
            st.session_state.profile['my_skills'] = st.multiselect(
                'Mes Compétences (+3 pts/compétence):', options=all_skills, default=current_profile_values['my_skills']
            )
            st.session_state.profile['target_roles'] = st.multiselect(
                'Mes Rôles Cibles (+10 pts):', options=all_work_titles, default=current_profile_values['target_roles']
            )
            st.session_state.profile['all_job_info'] = st.multiselect(
                'Infos sur le poste (+5 pts):', options=all_job_info_options, default=current_profile_values['all_job_info']
            )
            st.session_state.profile['all_company_info'] = st.multiselect(
                "Infos sur l'entreprise (+5 pts):", options=all_company_info_options, default=current_profile_values['all_company_info']
            )
        
        # Appliquer le score après que le profil a été défini/modifié
        df_display['match_score'] = df_display.apply(
            lambda row: calculate_match_score(row, st.session_state.profile), axis=1
        )
        
        st.write(f"Affichage de **{len(df_display)}** offres d'emploi filtrées, triées par score de pertinence.")

        # --- Logique de l'éditeur de données ---
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
        
        desired_order = ['match_score', 'title', 'company_name', 'status', 'contact_date']
        other_columns = [col for col in df_prepared.columns if col not in desired_order]
        df_prepared = df_prepared[desired_order + other_columns]

        # --- LOGIQUE DE SESSION STATE MISE À JOUR ---
        # On compare le profil actuel avec une copie pour détecter les changements
        profile_has_changed = st.session_state.get('profile') != st.session_state.get('last_profile')

        try:
            current_ids_in_state = set(st.session_state.df_editor_state['job_id'])
        except (KeyError, AttributeError):
            current_ids_in_state = set()
        newly_filtered_ids = set(df_prepared['job_id'])
        filters_have_changed = current_ids_in_state != newly_filtered_ids

        # On réinitialise l'état si les filtres OU le profil ont changé
        if 'df_editor_state' not in st.session_state or filters_have_changed or profile_has_changed:
            st.session_state.df_editor_state = df_prepared.copy()
            # On met à jour la "dernière version connue" du profil
            st.session_state.last_profile = st.session_state.profile.copy()


        max_possible_score = 10 + 5 + 5 + (3 * len(st.session_state.profile['my_skills']))
        if max_possible_score == 0: max_possible_score = 1

        edited_df = st.data_editor(
            st.session_state.df_editor_state,
            column_config={
                "match_score": st.column_config.ProgressColumn(
                    "Score", help="Score de pertinence basé sur votre profil",
                    min_value=0, max_value=max_possible_score, width="small"
                ),
                "title": st.column_config.Column(pinned=True, width="medium"),
                "company_name": st.column_config.Column(pinned=True, width="small"),
                "status": st.column_config.SelectboxColumn(
                    "Status", width="small", options=["Contacted", "Refused", "Positive"],
                    required=False, pinned=True,
                ),
                "contact_date": st.column_config.DateColumn("Contact Date", width="small"),
                "apply_link_1": st.column_config.LinkColumn("Lien pour postuler 1"),
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
            updated_tracker = st.session_state.df_editor_state[["job_id", "status", "contact_date", "notes"]].copy()
            updated_tracker.dropna(subset=['status'], inplace=True)
            if 'contact_date' in updated_tracker.columns:
                updated_tracker['contact_date'] = pd.to_datetime(updated_tracker['contact_date']).dt.strftime('%Y-%m-%d')
            updated_tracker = updated_tracker.astype(object).where(pd.notnull(updated_tracker), None)
            conn.client.table("tracker").upsert(updated_tracker.to_dict(orient="records")).execute()
            st.success("Your application progress has been saved to Supabase! 🚀")
            st.balloons() # <-- Ajout des ballons ici