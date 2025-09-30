import streamlit as st
import pandas as pd
import plotly.express as px
import ast

# --- Protection par mot de passe ---
def check_password():
    if "password_correct" in st.session_state and st.session_state["password_correct"]:
        return True

    st.header("🔑 Accès Protégé")
    password = st.text_input("Veuillez entrer le mot de passe pour accéder au dashboard.", type="password")

    if password == st.secrets.get("PASSWORD", "default_password"): # Utilise un mot de passe par défaut si le secret n'est pas défini
        st.session_state["password_correct"] = True
        st.rerun()
        return True
    elif password:
        st.error("Mot de passe incorrect.")
    
    return False

# --- Lancement de l'application ---
if check_password():
    # --- Fonctions de préparation et de plotting (regroupées pour la clarté) ---

    def categorize_seniority(seniority_list):
        if 'Non renseigné' in seniority_list: return "Non renseigné"
        if 'lead' in seniority_list: return "Lead"
        if 'senior' in seniority_list: return "Senior"
        if 'alternance' in seniority_list: return "Alternance"
        if 'junior' in seniority_list: return "Junior"
        if 'stage' in seniority_list: return "Stage"
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
    
    # ... (les autres fonctions de plotting restent identiques) ...
    def plot_seniorites_pie(df_to_plot):
        seniority_counts = df_to_plot['seniority_category'].value_counts()
        color_map = {'Senior': '#F6FF47', 'Lead': '#FF6347', 'Non renseigné': '#3FD655', 'Alternance': "#7A8C8D", 'junior': "#3FCCD6", 'Autre': 'blue'}
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
    
    # --- NOUVELLE LOGIQUE DE PRESET ---
    st.sidebar.subheader("Presets")
    
    # Le widget toggle contrôle directement l'état de la session
    st.sidebar.toggle("Recherche active de Thibault", key="preset_active")

    # Définition des valeurs par défaut et des presets
    DEFAULTS = {
        'consulting': 'Inclure tout',
        'schedule': 'Tous les types',
        'seniority_category': [],
        'titles': [],
        'category': 'Toutes les catégories',
        'sector': 'Tous les secteurs',
        'category_company': [],
    }
    
    PRESET_THIBAULT = {
        'consulting': 'Poste interne',
        'schedule': 'À plein temps',
        'seniority_category': ["Senior", "Non renseigné"],
        'titles': [
            "Data analyst", "Analyste de données", "Analyste décisionnel", "Business Analyst",
            "Power BI", "Analytics Engineer", "Développeur BI", "Business Intelligence", "Ingénieur BI"
            ],
        'category_company': ['GE','PME'],
        'sector': 'Tous les secteurs', # Non spécifié, donc on garde le défaut
        'company': 'Toutes les entreprises' # Non spécifié, donc on garde le défaut
    }

    # On choisit le dictionnaire de valeurs à utiliser en fonction du toggle
    current_values = PRESET_THIBAULT if st.session_state.preset_active else DEFAULTS

    # --- AFFICHAGE DES FILTRES AVEC LES BONNES VALEURS PAR DÉFAUT ---
    st.sidebar.subheader("Filtres sur le poste")
    is_consulting_options = ['Inclure tout'] + sorted(source_df['is_consulting_final'].dropna().unique().tolist())
    selected_is_consulting = st.sidebar.selectbox(
        'Filtrer par mention de consulting :',
        options=is_consulting_options,
        index=is_consulting_options.index(current_values['consulting'])
    )

    schedule_type_options = ['Tous les types'] + sorted(source_df['schedule_type'].dropna().unique().tolist())
    selected_schedule_type = st.sidebar.selectbox(
        'Filtrer par type de contrat :',
        options=schedule_type_options,
        index=schedule_type_options.index(current_values['schedule'])
    )

    seniority_options = sorted(source_df['seniority_category'].unique().tolist())
    selected_seniority = st.sidebar.multiselect(
        'Choisir des niveaux de séniorité :', 
        options=seniority_options,
        default=current_values['seniority_category']
    )

    all_work_titles = sorted(source_df.explode('work_titles')['work_titles'].dropna().unique().tolist())
    selected_work_titles = st.sidebar.multiselect(
        'Choisir des intitulés spécifiques :',
        options=all_work_titles,
        default=current_values['titles']
    )
    
    st.sidebar.subheader("Filtres sur la société")
    
    category_options = ['Toutes les catégories'] + sorted(source_df['categorie_entreprise'].dropna().unique().tolist())
    selected_category_company = st.sidebar.multiselect(
        "Filtrer par catégorie d'entreprise :",
        options=category_options,
        default=current_values['category_company']
    )

    selected_sector_company = st.sidebar.selectbox(
        "Filtrer par secteur d'entreprise :",
        options=['Tous les secteurs'] + sorted(source_df['section_activite_principale_detail'].dropna().unique().tolist())
        # Le default n'est pas spécifié, Streamlit prendra le premier
    )

    selected_company = st.sidebar.selectbox(
        'Filtrer par entreprise :',
        options=['Toutes les entreprises'] + sorted(source_df['company_name'].dropna().unique().tolist())
        # Le default n'est pas spécifié, Streamlit prendra le premier
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
        st.title("Explorer les offres")
        st.write(f"Affichage de **{len(df_display)}** offres d'emploi filtrées.")
        st.data_editor(
            df_display,
            column_config={
                "title": st.column_config.Column(pinned=True),
                "company_name": st.column_config.Column(pinned=True),
                "apply_link_1": st.column_config.LinkColumn("Lien pour postuler 1", help="Cliquez pour ouvrir le lien de l'offre", display_text="Postuler ici"),
                "apply_link_2": st.column_config.LinkColumn("Lien pour postuler 2", help="Cliquez pour ouvrir le lien de l'offre", display_text="Postuler ici")
            },
            hide_index=True,
            use_container_width=True
        )
