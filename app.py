import streamlit as st

# --- Protection par mot de passe ---
def check_password():
    # On vérifie si l'utilisateur est déjà authentifié
    if "password_correct" in st.session_state and st.session_state["password_correct"]:
        return True

    # Sinon, on affiche le formulaire de mot de passe
    st.header("🔑 Accès Protégé")
    password = st.text_input("Veuillez entrer le mot de passe pour accéder au dashboard.", type="password")

    # On vérifie si le mot de passe est correct (comparé au "Secret" que vous avez défini)
    if password == st.secrets["PASSWORD"]:
        st.session_state["password_correct"] = True
        st.rerun() # On recharge la page pour afficher l'application
        return True
    elif password:
        st.error("Mot de passe incorrect.")
    
    return False

# --- Lancement de l'application ---
if check_password():
    import pandas as pd
    import plotly.express as px
    import ast

    # --- Configuration de la page (doit être la première commande Streamlit) ---
    st.set_page_config(page_title="Dashboard Emploi Data", page_icon="📊", layout="wide")

    # --- Fonctions de préparation et de plotting ---

    def categorize_seniority(seniority_list):
        """Crée une catégorie de séniorité unique à partir d'une liste."""
        if not isinstance(seniority_list, list) or not seniority_list:
            return "Non renseigné"
        if 'lead' in seniority_list:
            return "Lead"
        if 'senior' in seniority_list:
            return "Senior"
        if 'alternance' in seniority_list:
            return "Alternance"
        if 'junior' in seniority_list:
            return "junior"
        # Ajoutez d'autres cas si nécessaire (ex: junior)
        return "Non renseigné"

    # --- Chargement et préparation des données (avec mise en cache) ---
    @st.cache_data
    def load_and_prepare_data(path):
        df = pd.read_csv(path)
        skill_columns = ['outils_bi', 'langages', 'cloud', 'modelisation', 'work_titles', 'type_contrat', 'seniorites']
        
        # LA LOGIQUE EST MAINTENANT INTÉGRÉE ICI
        def convert_string_to_list(val):
            # Cas 1 : La valeur est manquante, pas une chaîne, ou ne ressemble pas à une liste
            if pd.isna(val) or not isinstance(val, str) or not val.startswith('['):
                # On retourne directement la valeur pour les listes vides
                return ["Non renseigné"]
            
            # Cas 2 : La valeur est une chaîne qui ressemble à une liste
            try:
                result = ast.literal_eval(val)
                # Si la liste résultante est vide, on la remplace aussi
                if not result:
                    return ["Non renseigné"]
                return result
            except:
                # En cas d'erreur de formatage, on retourne la valeur par défaut
                return ["Non renseigné"]

        for col in skill_columns:
            if col in df.columns:
                df[col] = df[col].apply(convert_string_to_list)
        
        df['salaire_present'] = df['salary'].notna()
        df['seniority_category'] = df['seniorites'].apply(categorize_seniority)
        
        return df

    # --- Fonctions de plotting pour Array ---
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
                labels={'x': "Nombre d'offres", 'y': column_name.replace('_', ' ').capitalize()},
                text_auto=True
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info(f"Aucune compétence trouvée pour '{title}' dans cette sélection.")

    def plot_seniorites_pie(df_to_plot):
        seniority_counts = df_to_plot['seniority_category'].value_counts()
        
        # On définit les couleurs personnalisées
        color_map = {
            'Senior': '#F6FF47',
            'Lead': '#FF6347',
            'Non renseigné': '#3FD655',
            'Alternance': "#7A8C8D",
            'junior': "#3FCCD6",
            'Autre': 'blue' # Couleur par défaut pour les autres cas
        }
        
        fig = px.pie(
            values=seniority_counts.values, 
            names=seniority_counts.index,
            title="Répartition des niveaux de séniorité",
            color=seniority_counts.index, # On mappe les couleurs sur les noms de catégorie
            color_discrete_map=color_map
        )
        st.plotly_chart(fig, use_container_width=True)

    def plot_salary_pie(df_to_plot):
        """
        Génère un graphique à secteurs sécurisé pour la transparence des salaires,
        qui s'adapte dynamiquement aux filtres.
        """
        # Vérifier s'il y a des données à afficher
        if df_to_plot['salaire_present'].dropna().empty:
            st.info("Aucune donnée de salaire à afficher pour cette sélection.")
            return

        salary_counts = df_to_plot['salaire_present'].value_counts()

        label_map = {
            True: 'Salaire Mentionné',
            False: 'Salaire Non Mentionné'
        }

        color_map = {
            True: '#3FD655',  # Bleu pour les salaires présents
            False: '#FF6347'  # Rouge/Tomate pour les salaires absents
        }

        # 3. Construire le graphique en utilisant les mappings
        fig = px.pie(
            salary_counts,
            values=salary_counts.values,
            names=salary_counts.index.map(label_map),
            title="Transparence des salaires dans les offres",
            color=salary_counts.index,
            color_discrete_map=color_map
        )
        
        fig.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig, use_container_width=True)


    def plot_consulting_pie(df_to_plot):
        # Vérifier s'il y a des données à afficher après le filtrage
        if df_to_plot['is_consulting_final'].dropna().empty:
            st.info("Aucune donnée à afficher pour la répartition du consulting avec cette sélection.")
            return

        consulting_counts = df_to_plot['is_consulting_final'].value_counts()

        label_map = {
            'Consulting': 'Consulting',
            'Probablement consulting': 'Probablement consulting',
            'Poste interne': 'Poste interne'
        }

        color_map = {
            'Consulting': '#FF6347',
            'Probablement consulting': '#F6FF47',
            'Poste interne': '#3FD655'
        }
        
        fig = px.pie(
            consulting_counts, # Passer directement la Series Pandas
            values=consulting_counts.values, 
            names=consulting_counts.index.map(label_map), # Utilise l'index et le mappe aux bons noms
            title="Répartition du consulting",
            color=consulting_counts.index, # Attribuer la couleur en fonction de la valeur
            color_discrete_map=color_map   # Utiliser le dictionnaire de couleurs
        )
        
        # Améliorer l'affichage de la légende
        fig.update_traces(textposition='inside', textinfo='percent+label')
        
        st.plotly_chart(fig, use_container_width=True)

    # --- Fonctions de plotting pour autres valeurs ---
    def plot_value_counts_plotly(df_to_plot, column_name, top_n=10, title=""):
        """
        Génère un graphique à barres Plotly pour les colonnes à valeur unique,
        en incluant le comptage des valeurs non spécifiées.
        """
        # Vérification que la colonne existe et n'est pas vide
        if column_name not in df_to_plot.columns or df_to_plot[column_name].empty:
            st.warning(f"Pas de données à afficher pour '{title}'.")
            return

        # --- MODIFICATIONS PRINCIPALES ---
        # 1. Remplacer les valeurs NaN (None) par un libellé clair pour le graphique.
        # 2. Pas besoin de .explode() car la colonne contient des valeurs uniques.
        series_to_plot = df_to_plot[column_name].fillna('Non spécifié')
        
        # Compter les occurrences de chaque valeur, prendre le top N et trier pour l'affichage
        value_counts = series_to_plot.value_counts().nlargest(top_n).sort_values()

        if not value_counts.empty:
            fig = px.bar(
                value_counts, 
                x=value_counts.values, 
                y=value_counts.index,
                orientation='h', 
                title=title,
                labels={'x': "Nombre d'offres", 'y': column_name.replace('_', ' ').capitalize()},
                text_auto=True
            )
            # Améliorer la lisibilité des étiquettes
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

    # --- Initialisation de l'état de session pour la navigation ---
    if 'page' not in st.session_state:
        st.session_state.page = 'Synthèse des compétences'

    # --- Navigation entre les pages ---
    st.sidebar.header("Navigation")
    if st.sidebar.button("Synthèse des compétences", key="nav_competences"):
        st.session_state.page = 'Synthèse des compétences'
    if st.sidebar.button("Décomposition des offres", key="nav_decomposition"):
        st.session_state.page = 'Décomposition des offres'
    if st.sidebar.button("Données brutes", key="nav_donnees"):
        st.session_state.page = 'Données brutes'

    # --- Barre latérale (Sidebar) ---
    st.sidebar.header("Filtres")
    st.sidebar.subheader("Filtres sur le poste")
    selected_is_consulting = st.sidebar.selectbox(
        'Filtrer par mention de consulting :',
        options=['Inclure tout'] + sorted(source_df['is_consulting_final'].dropna().unique().tolist())
    )

    selected_schedule_type = st.sidebar.selectbox(
        'Filtrer par type de contrat :',
        options=['Tous les types'] + sorted(source_df['schedule_type'].dropna().unique().tolist())
    )

    seniority_options = ['Tous les niveaux'] + sorted(source_df['seniority_category'].unique().tolist())
    selected_seniority = st.sidebar.selectbox('Filtrer par séniorité :', options=seniority_options)

    all_work_titles = sorted(source_df.explode('work_titles')['work_titles'].dropna().unique().tolist())
    selected_work_titles = st.sidebar.multiselect(
        'Choisir des intitulés spécifiques :',
        options=all_work_titles,
        default=[] # Par défaut, la sélection est vide
    )
    
    st.sidebar.subheader("Filtres sur la société")
    selected_category_company = st.sidebar.selectbox(
        "Filtrer par catégorie d'entreprise :",
        options=['Toutes les catégories'] + sorted(source_df['categorie_entreprise'].dropna().unique().tolist())
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
    if selected_category_company != 'Toutes les catégories':
        df_display = df_display[df_display['categorie_entreprise'] == selected_category_company]    
    if selected_company != 'Toutes les entreprises':
        df_display = df_display[df_display['company_name'] == selected_company]
    if selected_schedule_type != 'Tous les types':
        df_display = df_display[df_display['schedule_type'] == selected_schedule_type]
    if selected_seniority != 'Tous les niveaux': 
        df_display = df_display[df_display['seniority_category'] == selected_seniority]
    if selected_work_titles:
        # On garde les lignes où il y a au moins une intersection entre la liste de la ligne
        # et la liste des titres sélectionnés.
        df_display = df_display[df_display['work_titles'].apply(
            lambda titles_in_row: any(title in titles_in_row for title in selected_work_titles)
        )]

    # --- Affichage de la page sélectionnée ---

    # Page 1 : Synthèse des compétences
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

    # Page 2 : Décomposition des offres
    elif st.session_state.page == 'Décomposition des offres':
        st.title("📄 Décomposition des offres")
        st.write(f"Analyse de **{len(df_display)}** offres d'emploi filtrées.")
        
        col1, col2 = st.columns(2)
        with col1:
            st.header("Intitulés de poste")
            plot_top_keywords_plotly(df_display, 'work_titles', top_n=20, title="Top des intitulés de poste")
        with col2:
            st.header("Seniorités")
            plot_seniorites_pie(df_display)

        st.markdown("---") 

        col1, col2 = st.columns(2)
        with col1:
            st.header("Type de contrat")
            plot_value_counts_plotly(df_display, 'schedule_type', top_n=20, title="Top des types de contrats")
        with col2:
            st.header("Consulting")
            plot_consulting_pie(df_display)

        st.markdown("---") 

        col1, col2 = st.columns(2)
        with col1:
            st.header("Top categorie d'entreprise")
            plot_value_counts_plotly(df_display, 'categorie_entreprise', top_n=20, title="Top des catégorie")
        with col2:
            st.header("Salaires")
            plot_salary_pie(df_display)

        st.markdown("---") 

        col1, col2 = st.columns(2)
        with col1:
            st.header("Analyse des entreprises")
            plot_value_counts_plotly(df_display, 'company_name', top_n=20, title="Top entreprises")
        with col2:
            st.header("Top activite")
            plot_value_counts_plotly(df_display, 'section_activite_principale_detail', top_n=20, title="Top des activités")

        st.markdown("---") 

    # Page 3 : Données brutes
    elif st.session_state.page == 'Données brutes':
        st.title("Explorer les offres")
        st.write(f"Affichage de **{len(df_display)}** offres d'emploi filtrées.")
        
        # --- MODIFICATION ICI ---
        # Remplacement de st.dataframe par st.data_editor pour rendre les liens cliquables
        st.data_editor(
            df_display,
            column_config={
                "title": st.column_config.Column(pinned=True),
                "company_name": st.column_config.Column(pinned=True),
                "apply_link_1": st.column_config.LinkColumn(
                    "Lien pour postuler 1",
                    help="Cliquez pour ouvrir le lien de l'offre",
                    display_text="Postuler ici"
                ),
                "apply_link_2": st.column_config.LinkColumn(
                    "Lien pour postuler 2",
                    help="Cliquez pour ouvrir le lien de l'offre",
                    display_text="Postuler ici"
                )
            },
            hide_index=True,
            use_container_width=True
        )