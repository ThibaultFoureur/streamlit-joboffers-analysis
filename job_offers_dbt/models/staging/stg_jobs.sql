-- This model cleans, prepares, and enriches the raw job offer data.

WITH source AS (

    SELECT * FROM {{ source('public', 'raw_jobs') }}

),

renamed_and_cast AS (

    SELECT
        -- IDs
        job_id,

        -- Job Info
        title,
        company_name,
        location,
        description,
        (title || ' ' || description) AS full_text,

        -- Extract from JSONB fields
        detected_extensions ->> 'posted_at' AS posted_at,
        detected_extensions ->> 'salary' AS salary,
        detected_extensions ->> 'schedule_type' AS original_schedule_type,
        
        apply_options -> 0 ->> 'link' AS apply_link_1,
        apply_options -> 1 ->> 'link' AS apply_link_2,

        -- Raw columns for future reference
        via,
        share_link,
        thumbnail,
        created_at

    FROM source

),

salary_calculations AS (

    SELECT
        job_id,
        salary,

        -- 1. Standardize string for parsing
        LOWER(REPLACE(REPLACE(REPLACE(salary, ',', '.'), ' ', ''), '€', '')) AS cleaned_salary,

        -- 2. Determine the multiplier based on the period (day, month, year)
        CASE
            WHEN salary ILIKE '%par jour%' OR salary ILIKE '%per day%' THEN 220 -- Assuming ~220 working days/year
            WHEN salary ILIKE '%par mois%' OR salary ILIKE '%per month%' THEN 12
            ELSE 1
        END AS multiplier,

        -- 3. Extract numeric values using REGEX, keeping only digits and the decimal point
        -- Use NULLIF to handle cases where no numbers are found, preventing errors
        NULLIF(REGEXP_REPLACE(
            REPLACE(
                CASE
                        -- If there's a range (using 'à'), take the first part
                        WHEN salary LIKE '%à%' THEN SPLIT_PART(LOWER(salary), 'à', 1)
                        ELSE salary
                    END,
                ',', '.'),
        '[^0-9.]', '', 'g'), '')::NUMERIC AS min_value,

        NULLIF(REGEXP_REPLACE(
            CASE
                -- If there's a range, take the second part
                WHEN salary LIKE '%à%' THEN SPLIT_PART(LOWER(salary), 'à', 2)
                -- Otherwise, it's a single value, so max is same as min
                ELSE salary
            END,
        '[^0-9.]', '', 'g'), '')::NUMERIC AS max_value,

        -- 4. Check if the salary was mentioned in thousands ('k')
        CASE WHEN salary LIKE '%k%' THEN 1000 ELSE 1 END AS k_multiplier

    FROM renamed_and_cast
    WHERE salary IS NOT NULL

),

annual_salary AS (

    SELECT
        job_id,
        salary,
        -- 5. Calculate the final annual salary, including a heuristic for cases where 'k' was likely omitted
        CASE
            -- If the calculated yearly salary is less than 1000, it's likely the 'k' was missing
            WHEN (min_value * k_multiplier * multiplier) < 1000 AND multiplier = 1
            THEN (min_value * k_multiplier * multiplier) * 1000
            ELSE (min_value * k_multiplier * multiplier)
        END AS annual_min_salary,

        CASE
            WHEN (max_value * k_multiplier * multiplier) < 1000 AND multiplier = 1
            THEN (max_value * k_multiplier * multiplier) * 1000
            ELSE (max_value * k_multiplier * multiplier)
        END AS annual_max_salary

    FROM salary_calculations
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
        user_configs AS config,
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
        renamed_and_cast AS jobs
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
),

final_enrichments AS (
    SELECT
        r.*,
        a.annual_min_salary,
        a.annual_max_salary,
        COALESCE(agg_skills.found_skills, '{}'::jsonb) AS found_skills, -- Use the new dynamic skills object
        CASE WHEN a.salary IS NOT NULL THEN TRUE ELSE FALSE END AS is_salary_mentioned,
        CASE
            WHEN r.original_schedule_type ILIKE '%Stage%' THEN 'Internship'
            WHEN r.original_schedule_type ILIKE '%Prestataire%' THEN 'Contractor'
            WHEN r.original_schedule_type ILIKE '%À temps partiel%' THEN 'Part-time'
            WHEN r.original_schedule_type ILIKE '%À plein temps%' THEN 'Full-time'
            ELSE r.original_schedule_type
        END AS schedule_type,
        -- Categorize job titles (this logic remains the same)
        ARRAY(
            SELECT unnested FROM (
                SELECT UNNEST(ARRAY[
                    CASE WHEN lower(r.title) ILIKE ANY (ARRAY['%data scientist%', '%machine learning%']) THEN 'Data Scientist/AI' END,
                    CASE WHEN lower(r.title) ILIKE ANY (ARRAY['%analytics engineer%']) THEN 'Analytics Engineer' END,
                    CASE WHEN lower(r.title) ILIKE ANY (ARRAY['%data engineer%', '%data ops%']) THEN 'Data Engineer/Platform' END,
                    CASE WHEN lower(r.title) ILIKE ANY (ARRAY['%bi%', '%décisionnel%']) THEN 'BI/Decision Support Specialist' END,
                    CASE WHEN lower(r.title) ILIKE ANY (ARRAY['%business analyst%']) THEN 'Business/Functional Analyst' END,
                    CASE WHEN lower(r.title) ILIKE ANY (ARRAY['%data analyst%']) THEN 'Data Analyst' END
                ]) AS unnested
            ) AS subquery WHERE unnested IS NOT NULL
        ) AS work_titles,
        -- Categorize seniority (this logic remains the same)
        CASE
            WHEN lower(r.title) ILIKE ANY (ARRAY['%stage%', '%internship%', '%alternance%']) THEN 'Intern/Apprentice'
            WHEN lower(r.title) ILIKE ANY (ARRAY['%senior%', '%expert%']) THEN 'Senior/Expert'
            WHEN lower(r.title) ILIKE ANY (ARRAY['%lead%', '%manager%', '%directeur%']) THEN 'Lead/Manager'
            WHEN lower(r.title) ILIKE '%junior%' THEN 'Junior'
            ELSE 'Not specified'
        END AS seniority_category
    FROM
        renamed_and_cast AS r
    LEFT JOIN
        annual_salary AS a ON r.job_id = a.job_id
    LEFT JOIN
        aggregated_skills AS agg_skills ON r.job_id = agg_skills.job_id
)

SELECT 
    -- Select all columns from the final_enrichments CTE
    *,
    -- Add a final check to ensure the categorized work_titles array is never empty
    CASE 
        WHEN ARRAY_LENGTH(work_titles, 1) IS NULL THEN ARRAY['Other']
        ELSE work_titles 
    END AS work_titles_final
FROM final_enrichments