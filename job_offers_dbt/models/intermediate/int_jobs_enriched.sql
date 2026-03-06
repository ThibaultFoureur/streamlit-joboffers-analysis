-- This model centralizes all enrichments: categories, seniority, and joins with other intermediate models
WITH jobs AS (
    SELECT * FROM {{ ref('stg_jobs') }}
),

dates AS (
    SELECT * FROM {{ ref('int_jobs_dates') }}
),

salaries AS (
    SELECT * FROM {{ ref('int_jobs_salaries') }}
),

skills AS (
    SELECT * FROM {{ ref('int_jobs_skills') }}
),

enrichments AS (
    SELECT
        j.*,
        d.posted_at,
        s.salary,
        s.annual_min_salary,
        s.annual_max_salary,
        CASE WHEN s.annual_min_salary IS NOT NULL THEN TRUE ELSE FALSE END AS is_salary_mentioned,
        COALESCE(sk.found_skills, '{}'::jsonb) AS found_skills,

        -- 1. Standardizing Schedule Type
        CASE
            WHEN j.raw_schedule_type ILIKE '%Stage%' THEN 'Internship'
            WHEN j.raw_schedule_type ILIKE '%Prestataire%' THEN 'Contractor'
            WHEN j.raw_schedule_type ILIKE '%À temps partiel%' THEN 'Part-time'
            WHEN j.raw_schedule_type ILIKE '%À plein temps%' THEN 'Full-time'
            ELSE j.raw_schedule_type
        END AS schedule_type,

        -- 2. Categorizing Seniority
        CASE
            WHEN LOWER(j.title) ILIKE ANY (ARRAY['%stage%', '%internship%', '%alternance%']) THEN 'Intern/Apprentice'
            WHEN LOWER(j.title) ILIKE ANY (ARRAY['%senior%', '%expert%']) THEN 'Senior/Expert'
            WHEN LOWER(j.title) ILIKE ANY (ARRAY['%lead%', '%manager%', '%directeur%']) THEN 'Lead/Manager'
            WHEN LOWER(j.title) ILIKE '%junior%' THEN 'Junior'
            ELSE 'Not specified'
        END AS seniority_category,

        -- 3. Mapping Work Titles (Array logic)
        ARRAY(
            SELECT unnested FROM (
                SELECT UNNEST(ARRAY[
                    CASE WHEN LOWER(j.title) ILIKE ANY (ARRAY['%data scientist%', '%machine learning%']) THEN 'Data Scientist/AI' END,
                    CASE WHEN LOWER(j.title) ILIKE ANY (ARRAY['%analytics engineer%']) THEN 'Analytics Engineer' END,
                    CASE WHEN LOWER(j.title) ILIKE ANY (ARRAY['%data engineer%', '%data ops%']) THEN 'Data Engineer/Platform' END,
                    CASE WHEN LOWER(j.title) ILIKE ANY (ARRAY['%bi%', '%décisionnel%']) THEN 'BI/Decision Support Specialist' END,
                    CASE WHEN LOWER(j.title) ILIKE ANY (ARRAY['%business analyst%']) THEN 'Business/Functional Analyst' END,
                    CASE WHEN LOWER(j.title) ILIKE ANY (ARRAY['%data analyst%']) THEN 'Data Analyst' END
                ]) AS unnested
            ) AS subquery WHERE unnested IS NOT NULL
        ) AS work_titles

    FROM jobs j
    LEFT JOIN dates d ON j.job_id = d.job_id
    LEFT JOIN salaries s ON j.job_id = s.job_id
    LEFT JOIN skills sk ON j.job_id = sk.job_id
)

SELECT 
    *,
    -- Final safety check for work titles
    CASE 
        WHEN ARRAY_LENGTH(work_titles, 1) IS NULL THEN ARRAY['Other']
        ELSE work_titles 
    END AS work_titles_final
FROM enrichments