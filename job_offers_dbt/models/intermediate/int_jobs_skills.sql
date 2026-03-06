WITH jobs AS (
    SELECT 
        job_id,
        (title || ' ' || description) AS full_text 
    
    FROM {{ ref('stg_jobs') }}
),

config AS (
    SELECT
        *
    FROM  {{ ref('stg_user_configs') }} 
),

all_user_skills AS (
    SELECT
        config.user_id,
        category_skills.category,
        -- This is the final, clean English name we want to keep
        alias_skills.canonical_name,
        -- This is the specific French or English term we will search for
        LOWER(skills.search_alias) AS keyword
    FROM
        config,
        -- 1. Unnest top-level categories (e.g., 'soft_skills')
        LATERAL jsonb_each(config.search_skills) AS category_skills(category, skill_objects)
        -- 2. Unnest canonical names and their alias arrays (e.g., 'organization', '["organization", "organisation"]')
        , LATERAL jsonb_each(category_skills.skill_objects) AS alias_skills(canonical_name, alias_array)
        -- 3. Unnest the alias array into individual search terms (e.g., 'organization', 'organisation')
        , LATERAL jsonb_array_elements_text(alias_skills.alias_array) AS skills(search_alias)
),

matched_skills AS (
    SELECT
        jobs.job_id,
        skills.category,
        skills.canonical_name AS skill_name
    FROM
        jobs
    LEFT JOIN
        all_user_skills AS skills
        ON CASE
            -- For any keyword 3 characters or less, use strict whole-word regex
            WHEN LENGTH(skills.keyword) <= 3 THEN jobs.full_text ~* ('\m' || skills.keyword || '\M')
            
            -- For all longer keywords, use the more flexible ILIKE
            ELSE jobs.full_text ILIKE '%' || skills.keyword || '%'
           END
    WHERE
        skills.keyword IS NOT NULL
),

aggregated_skills AS (
    SELECT
        job_id,
        -- This function builds a JSON object from the aggregated key/value pairs
        jsonb_object_agg(
            category,
            keyword_array
        ) AS found_skills
    FROM (
        -- First, group by category to create an array of unique keywords found for that category
        SELECT
            job_id,
            category,
            jsonb_agg(DISTINCT skill_name) AS keyword_array
        FROM
            matched_skills
        GROUP BY
            job_id, category
    ) AS grouped_by_category
    GROUP BY
        job_id
)

SELECT job_id, found_skills FROM aggregated_skills