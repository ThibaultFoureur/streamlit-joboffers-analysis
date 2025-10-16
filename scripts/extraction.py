import os
import time
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client
from serpapi import GoogleSearch
import requests
import re

# --- CONSTANTS ---
MAX_PAGES_PER_QUERY = int(os.environ.get('MAX_PAGES_PER_QUERY', '1'))

# --- SERVICE CONNECTIONS ---
load_dotenv()
supabase_url: str = os.getenv("SUPABASE_URL")
supabase_key: str = os.getenv("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)
serpapi_key: str = os.getenv("SERPAPI_KEY")
print("✅ Service connections established.")

# --- JOB EXTRACTION FUNCTIONS ---
def fetch_raw_jobs_paginated(query: str, max_pages: int) -> list:
    """Fetches all raw job listings from SerpApi for a given query, handling pagination."""
    # (This function remains the same as the previous version)
    print(f"🔍 Searching for jobs with query: '{query}'")
    params = {"engine": "google_jobs", "q": query, "api_key": serpapi_key, "gl": "fr", "hl": "fr"}
    all_jobs_for_query, page_num = [], 1
    while True:
        print(f"  📄 Fetching page {page_num}...")
        search = GoogleSearch(params)
        results = search.get_dict()
        if 'error' in results:
            print(f"  ❌ Error for this search: {results['error']}"); break
        jobs_on_page = results.get('jobs_results', [])
        if not jobs_on_page:
            print("  ⏹️ No more jobs found for this query."); break
        all_jobs_for_query.extend(jobs_on_page)
        print(f"    -> {len(jobs_on_page)} jobs added from this page.")
        if page_num >= max_pages:
            print(f"  ⚠️ Reached the limit of {max_pages} pages."); break
        page_num += 1
        next_page_token = results.get('serpapi_pagination', {}).get('next_page_token')
        if next_page_token:
            params['next_page_token'] = next_page_token; time.sleep(1)
        else:
            print("  ⏹️ This was the last page of results."); break
    return all_jobs_for_query

# --- COMPANY ENRICHMENT FUNCTIONS (from your notebook) ---
def clean_company_name(name: str) -> str:
    """Cleans a company name to optimize for API search."""
    if not isinstance(name, str): return None
    if name.strip() == "EY": return "EY "
    
    clean_name = name.lower()
    terms_to_remove = [
        'jobs', 'digital', 'en', 'fonctions centrales', 'france', 'recrutement',
        '| b corp™', 'sas', 's.a.s.', 'gmbh', 'limited', 'nv', 'epic', 'groupe',
        'h/f', r'\(siège\)', r'\| groupe edg', 'corporate & institutional banking'
    ]
    for term in terms_to_remove:
        clean_name = re.sub(r'\b' + re.escape(term) + r'\b', '', clean_name, flags=re.IGNORECASE)

    separators = ['-', '|', '(', ',']
    for sep in separators:
        if sep in clean_name:
            clean_name = clean_name.split(sep)[0]

    clean_name = clean_name.strip().title()
    return name if len(clean_name) < 3 else clean_name

def get_company_info(company_name: str) -> dict:
    """Cleans the company name BEFORE calling the API."""
    cleaned_name = clean_company_name(company_name)
    if not cleaned_name: return None

    base_url = "https://recherche-entreprises.api.gouv.fr/search"
    params = {"q": cleaned_name, "minimal": "true"}

    try:
        time.sleep(0.5) # Politeness delay
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()

        if data and 'results' in data and data['results']:
            results_list = data['results']
            # Sort results to prioritize companies with employee count data
            sorted_results = sorted(
                results_list,
                key=lambda x: ((x.get('tranche_effectif_salarie') or '00') != 'NN', x.get('tranche_effectif_salarie') or '00'),
                reverse=True
            )
            return sorted_results[0]
        else:
            return None
    except requests.exceptions.RequestException as e:
        print(f"  -> API Request failed for '{cleaned_name}': {e}")
        return None
    except Exception as e:
        print(f"  -> An unexpected error occurred for '{cleaned_name}': {e}")
        return None

# --- MAIN SCRIPT ---
if __name__ == "__main__":
    
    # =========================================================================
    # PART 1: FETCH AND LOAD NEW JOB OFFERS BASED ON USER CONFIGS
    # =========================================================================
    print("🚀 Starting Part 1: Fetching New Job Offers")
    
    # UPDATED: Fetch all user search configurations from Supabase
    print("Fetching user search configurations...")
    try:
        configs_response = supabase.table("user_configs").select("user_id, search_queries, search_location").execute()
        search_configs = configs_response.data
        if not search_configs:
            print("⏹️ No active user configurations found. Exiting job search.")
            # We still proceed to the company enrichment part
        else:
            print(f"Found {len(search_configs)} configurations to process.")
    except Exception as e:
        print(f"❌ Error fetching user configurations: {e}")
        search_configs = [] # Ensure the script can continue to company enrichment

    all_new_jobs_to_load = []
    all_new_job_user_links = [] # UPDATED: List to store user-job relationships

    if search_configs:
        try:
            response = supabase.table('raw_jobs').select('job_id').execute()
            existing_job_ids = {item['job_id'] for item in response.data}
            print(f"Found {len(existing_job_ids)} existing job IDs in 'raw_jobs'.")
        except Exception as e:
            print(f"⚠️ Could not fetch existing job IDs. Error: {e}")
            existing_job_ids = set()

        # UPDATED: Loop through each user's configuration
        for config in search_configs:
            user_id = config['user_id']
            location = config['search_location']
            job_titles = config.get('search_queries', [])
            
            if not all([user_id, location, job_titles]):
                print(f"⚠️ Skipping config due to missing data: {config}")
                continue

            print(f"\nProcessing config for user: {user_id}")

            # UPDATED: Loop through the job titles for the current user
            for title in job_titles:
                # UPDATED: Dynamically build the query string
                query = f'"{title}" {location}'
                
                jobs_from_api = fetch_raw_jobs_paginated(query, MAX_PAGES_PER_QUERY)
                if not jobs_from_api: continue

                df = pd.DataFrame(jobs_from_api)
                if 'job_id' not in df.columns: continue
                df.drop_duplicates(subset=['job_id'], keep='first', inplace=True)

                # 1. Identify jobs whose *details* we haven't stored yet
                new_jobs_details_df = df[~df['job_id'].isin(existing_job_ids)]
                if not new_jobs_details_df.empty:
                    print(f"  ✨ Found {len(new_jobs_details_df)} new job *details* for query '{query}'.")
                    all_new_jobs_to_load.extend(new_jobs_details_df.to_dict(orient='records'))
                    # Add the newly found job IDs to our set to avoid re-adding them from another query
                    existing_job_ids.update(new_jobs_details_df['job_id'])

                # 2. Create the user-job links for *all* jobs found by this query
                for job_id in df['job_id']:
                    all_new_job_user_links.append({"user_id": user_id, "job_id": job_id})

            print("-" * 40)

    # UPDATED: Load job details first, then the links
    if not all_new_jobs_to_load:
        print("✅ No new job details to add.")
    else:
        raw_jobs_df = pd.DataFrame(all_new_jobs_to_load).drop_duplicates(subset=['job_id'])
        print(f"\nUpserting {len(raw_jobs_df)} new and unique job details into 'raw_jobs' table...")
        raw_jobs_df = raw_jobs_df.astype(object).where(pd.notnull(raw_jobs_df), None)
        try:
            supabase.table('raw_jobs').upsert(raw_jobs_df.to_dict(orient='records')).execute()
            print("✅ Job details load successful!")
        except Exception as e:
            print(f"❌ Error during 'raw_jobs' load: {e}")
    
    if not all_new_job_user_links:
        print("✅ No new user-job links to create.")
    else:
        links_df = pd.DataFrame(all_new_job_user_links).drop_duplicates()
        print(f"Upserting {len(links_df)} user-job links into 'raw_job_user_links'...")
        try:
            supabase.table('raw_job_user_links').upsert(links_df.to_dict(orient='records')).execute()
            print("✅ User-job links load successful!")
        except Exception as e:
            print(f"❌ Error during 'raw_job_user_links' load: {e}")

    # =========================================================================
    # PART 2: FETCH AND LOAD NEW COMPANY INFORMATION
    # =========================================================================
    print("\n🚀 Starting Part 2: Enriching Company Information")

    # 1. Get all unique company names from raw_jobs
    all_companies_response = supabase.table('raw_jobs').select('company_name').execute()
    unique_company_names_in_jobs = {
        item['company_name'] for item in all_companies_response.data if item['company_name']
    }

    # 2. Get company names already in raw_companies
    try:
        existing_companies_response = supabase.table('raw_companies').select('company_name').execute()
        existing_company_names = {item['company_name'] for item in existing_companies_response.data}
        print(f"Found {len(existing_company_names)} companies already in 'raw_companies'.")
    except Exception as e:
        print(f"⚠️ Could not fetch existing companies, assuming all are new. Error: {e}")
        existing_company_names = set()
        
    # 3. Determine which new companies to fetch
    new_companies_to_fetch = unique_company_names_in_jobs - existing_company_names
    
    if not new_companies_to_fetch:
        print("✅ No new companies to enrich. Script finished.")
    else:
        print(f"Found {len(new_companies_to_fetch)} new companies to fetch information for.")
        new_companies_data = []
        for name in new_companies_to_fetch:
            print(f"  Fetching info for: {name}")
            info = get_company_info(name)
            new_companies_data.append({
                'company_name': name,
                'company_info': info # Store the entire JSON response
            })

        # 5. Load new company data into raw_companies
        print(f"\nLoading {len(new_companies_data)} new companies into 'raw_companies'...")
        df_new_companies = pd.DataFrame(new_companies_data)
        df_new_companies = df_new_companies.astype(object).where(pd.notnull(df_new_companies), None)
        try:
            # Upsert is safer in case the script is run multiple times in parallel
            supabase.table('raw_companies').upsert(df_new_companies.to_dict(orient='records')).execute()
            print("✅ Part 2 Load successful!")
        except Exception as e:
            print(f"❌ Error during 'raw_companies' load: {e}")
    
    print("\n✅ Script finished.")