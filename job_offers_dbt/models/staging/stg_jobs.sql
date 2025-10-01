-- This model cleans and prepares the raw job offer data.

with source as (

    select * from {{ source('public', 'raw_jobs') }}

),

renamed_and_cast as (

    select
        -- IDs
        job_id,

        -- Job Info
        title,
        company_name,
        location,
        description,
        (title || ' ' || description) as full_text,

        -- Extract from JSONB fields
        detected_extensions ->> 'posted_at' as posted_at,
        detected_extensions ->> 'salary' as salary,
        detected_extensions ->> 'schedule_type' as schedule_type,
        
        apply_options -> 0 ->> 'link' as apply_link_1,
        apply_options -> 1 ->> 'link' as apply_link_2,

        -- Raw columns for future reference
        via,
        share_link,
        thumbnail,
        created_at

    from source

),

keywords_extracted as (

    select
        *,

        -- Logic to extract programming languages into an array
        ARRAY(
            SELECT unnested FROM (
                SELECT UNNEST(ARRAY[
                    CASE WHEN full_text ILIKE '%python%' THEN 'python' END,
                    CASE WHEN full_text ILIKE '%sql%' THEN 'sql' END,
                    CASE WHEN full_text ILIKE '% r %' THEN 'r' END,
                    CASE WHEN full_text ILIKE '%scala%' THEN 'scala' END,
                    CASE WHEN full_text ILIKE '%sas%' THEN 'sas' END,
                    CASE WHEN full_text ILIKE '%vba%' THEN 'vba' END,
                    CASE WHEN full_text ILIKE '%dax%' THEN 'dax' END,
                    CASE WHEN full_text ILIKE '%mdx%' THEN 'mdx' END
                ]) AS unnested
            ) AS subquery WHERE unnested IS NOT NULL
        ) AS languages,
        
        -- Logic for BI tools
        ARRAY(
            SELECT unnested FROM (
                SELECT UNNEST(ARRAY[
                    CASE WHEN full_text ILIKE '%tableau%' THEN 'tableau' END,
                    CASE WHEN full_text ILIKE ANY (ARRAY['%power bi%', '%powerbi%', '%pbi%']) THEN 'power bi' END,
                    CASE WHEN full_text ILIKE '%looker%' THEN 'looker' END,
                    CASE WHEN full_text ILIKE '%qlik%' THEN 'qlik' END,
                    CASE WHEN full_text ILIKE ANY (ARRAY['%business objects%', '% bo %']) THEN 'business objects' END,
                    CASE WHEN full_text ILIKE '%excel%' THEN 'excel' END,
                    CASE WHEN full_text ILIKE '%dataiku%' THEN 'dataiku' END
                ]) AS unnested
            ) AS subquery WHERE unnested IS NOT NULL
        ) AS bi_tools,

        -- Logic for cloud platforms
        ARRAY(
            SELECT unnested FROM (
                SELECT UNNEST(ARRAY[
                    CASE WHEN full_text ILIKE '%aws%' THEN 'aws' END,
                    CASE WHEN full_text ILIKE '%azure%' THEN 'azure' END,
                    CASE WHEN full_text ILIKE '%gcp%' THEN 'gcp' END,
                    CASE WHEN full_text ILIKE '%snowflake%' THEN 'snowflake' END,
                    CASE WHEN full_text ILIKE '%databricks%' THEN 'databricks' END
                ]) AS unnested
            ) AS subquery WHERE unnested IS NOT NULL
        ) AS cloud_platforms,

        -- Logic for data modeling tools and concepts
        ARRAY(
            SELECT unnested FROM (
                SELECT UNNEST(ARRAY[
                    CASE WHEN full_text ILIKE '%dbt%' THEN 'dbt' END,
                    CASE WHEN full_text ILIKE '%elt%' THEN 'elt' END,
                    CASE WHEN full_text ILIKE '%etl%' THEN 'etl' END,
                    CASE WHEN full_text ILIKE ANY (ARRAY['%data modeling%', '%modélisation%']) THEN 'data modeling' END,
                    CASE WHEN full_text ILIKE '%talend%' THEN 'talend' END,
                    CASE WHEN full_text ILIKE '%informatica%' THEN 'informatica' END,
                    CASE WHEN full_text ILIKE '%ssis%' THEN 'ssis' END,
                    CASE WHEN full_text ILIKE '%data warehouse%' THEN 'data warehouse' END,
                    CASE WHEN full_text ILIKE '%datamart%' THEN 'datamart' END,
                    CASE WHEN full_text ILIKE '%postgresql%' THEN 'postgresql' END,
                    CASE WHEN full_text ILIKE '%mysql%' THEN 'mysql' END,
                    CASE WHEN full_text ILIKE '%sql server%' THEN 'sql server' END,
                    CASE WHEN full_text ILIKE '%oracle%' THEN 'oracle' END,
                    CASE WHEN full_text ILIKE '%mongodb%' THEN 'mongodb' END
                ]) AS unnested
            ) AS subquery WHERE unnested IS NOT NULL
        ) AS data_modelization

    from renamed_and_cast
),

final as (
    select
        *,

        -- CORRECTED LOGIC: Categorize job titles into an array of all matches
        ARRAY(
            SELECT unnested FROM (
                SELECT UNNEST(ARRAY[
                    CASE WHEN lower(title) ILIKE ANY (ARRAY['%data scientist%', '%machine learning%', '%ml engineer%', '%ai engineer%', '%ia%', '%deep learning%']) THEN 'Data Scientist/IA' END,
                    CASE WHEN lower(title) ILIKE ANY (ARRAY['%analytics engineer%', '%analytic engineer%']) THEN 'Analytics Engineer' END,
                    CASE WHEN lower(title) ILIKE ANY (ARRAY['%data engineer%', '%data ops%', '%mlops%', '%devops%', '%sre%', '%etl%']) THEN 'Data Engineer/Platform' END,
                    CASE WHEN lower(title) ILIKE ANY (ARRAY['%bi%', '%décisionnel%', '%business intelligence%']) THEN 'BI Specialist' END,
                    CASE WHEN lower(title) ILIKE ANY (ARRAY['%business analyst%', '%functional analyst%']) THEN 'Business/Functional Analyst' END,
                    CASE WHEN lower(title) ILIKE ANY (ARRAY['%data analyst%', '%analyste de données%']) THEN 'Data Analyst' END
                ]) AS unnested
            ) AS subquery WHERE unnested IS NOT NULL
        ) AS work_titles,

        -- Categorize seniority (First match win)
        CASE
            WHEN lower(title) ILIKE ANY (ARRAY['%stage%', '%stagiaire%', '%internship%', '%apprenti%', '%alternance%']) THEN 'Intern/Apprentice'
            WHEN lower(title) ILIKE ANY (ARRAY['%senior%', '%confirmé%', '%expert%', '%principal%']) THEN 'Senior/Expert'
            WHEN lower(title) ILIKE ANY (ARRAY['%lead%', '%head of%', '%responsable%', '%manager%', '%directeur%']) THEN 'Lead/Manager'
            WHEN lower(title) ILIKE '%junior%' THEN 'Junior'
            ELSE 'Not specified'
        END AS seniority_category -- Changed to a single value, not an array

    from keywords_extracted
)

select 
    *,
    -- Add a final check to ensure work_titles is never empty
    CASE 
        WHEN ARRAY_LENGTH(work_titles, 1) IS NULL THEN ARRAY['Other']
        ELSE work_titles 
    END as work_titles_final
from final