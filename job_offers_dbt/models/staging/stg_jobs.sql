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

keywords_extracted AS (

    SELECT
        r.*,
        a.annual_min_salary,
        a.annual_max_salary,

        -- A flag to easily filter for jobs with salary info
        CASE WHEN a.salary IS NOT NULL THEN TRUE ELSE FALSE END AS is_salary_mentioned,

        -- Translate the schedule type from French to English - First found win
        CASE
            WHEN r.original_schedule_type ILIKE '%Stage%' THEN 'Internship'
            WHEN r.original_schedule_type ILIKE '%Prestataire%' THEN 'Contractor'
            WHEN r.original_schedule_type ILIKE '%À temps partiel%' THEN 'Part-time'
            WHEN r.original_schedule_type ILIKE '%À plein temps%' THEN 'Full-time'
            ELSE r.original_schedule_type -- Fallback for untranslated values
        END AS schedule_type,

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

    FROM renamed_and_cast AS r
    LEFT JOIN annual_salary AS a ON r.job_id = a.job_id
),

final AS (
    SELECT
        *,

        -- Categorize job titles into an array of all matches, using English keywords
        ARRAY(
            SELECT unnested FROM (
                SELECT UNNEST(ARRAY[
                    CASE WHEN lower(title) ILIKE ANY (ARRAY['%data scientist%', '%machine learning%', '%ml engineer%', '%ai engineer%', '%ia%', '%deep learning%']) THEN 'Data Scientist/AI' END,
                    CASE WHEN lower(title) ILIKE ANY (ARRAY['%analytics engineer%', '%analytic engineer%']) THEN 'Analytics Engineer' END,
                    CASE WHEN lower(title) ILIKE ANY (ARRAY['%data engineer%', '%data ops%', '%mlops%', '%devops%', '%sre%', '%etl%']) THEN 'Data Engineer/Platform' END,
                    CASE WHEN lower(title) ILIKE ANY (ARRAY['%bi%', '%décisionnel%', '%business intelligence%']) THEN 'BI/Decision Support Specialist' END,
                    CASE WHEN lower(title) ILIKE ANY (ARRAY['%business analyst%', '%functional analyst%']) THEN 'Business/Functional Analyst' END,
                    CASE WHEN lower(title) ILIKE ANY (ARRAY['%data analyst%', '%analyste de données%']) THEN 'Data Analyst' END
                ]) AS unnested
            ) AS subquery WHERE unnested IS NOT NULL
        ) AS work_titles,

        -- Categorize seniority, translating French keywords
        CASE
            WHEN lower(title) ILIKE ANY (ARRAY['%stage%', '%stagiaire%', '%internship%', '%apprenti%', '%alternance%']) THEN 'Intern/Apprentice'
            WHEN lower(title) ILIKE ANY (ARRAY['%senior%', '%confirmé%', '%expert%', '%principal%']) THEN 'Senior/Expert'
            WHEN lower(title) ILIKE ANY (ARRAY['%lead%', '%head of%', '%responsable%', '%manager%', '%directeur%']) THEN 'Lead/Manager'
            WHEN lower(title) ILIKE '%junior%' THEN 'Junior'
            ELSE 'Not specified'
        END AS seniority_category

    FROM keywords_extracted
)

SELECT 
    -- Select all columns from the final CTE
    *,
    -- Add a final check to ensure the categorized work_titles array is never empty
    CASE 
        WHEN ARRAY_LENGTH(work_titles, 1) IS NULL THEN ARRAY['Other']
        ELSE work_titles 
    END AS work_titles_final
FROM final