-- Final gold model for Streamlit analysis
WITH enriched_jobs AS (
    SELECT * FROM {{ ref('int_jobs_enriched') }}
),

companies AS (
    SELECT * FROM {{ ref('stg_companies') }}
),

final as (

    select
        -- Select and reorder the final columns
        j.title,
        j.company_name,
        c.company_category,
        c.activity_section_details,
        j.location,
        j.via,
        j.is_salary_mentioned,
        j.salary,
        j.annual_min_salary,
        j.annual_max_salary,
        j.work_titles_final,
        j.schedule_type,
        j.posted_at,
        j.seniority_category,
        j.found_skills,

        -- Final business logic for consulting status
        CASE
            WHEN lower(j.title) ILIKE '%consult%' THEN 'Consulting'
            WHEN (lower(j.title) ILIKE ANY (ARRAY['%consultant%', '%consulting%'])) AND c.is_consulting_company THEN 'Consulting'
            WHEN (lower(j.title) ILIKE ANY (ARRAY['%consultant%', '%consulting%'])) OR c.is_consulting_company THEN 'Probably consulting'
            ELSE 'Internal position'
        END as consulting_status,

        -- Keep IDs and useful text fields at the end
        j.description,
        --j.full_text,
        j.job_id,
        j.apply_link_1,
        j.apply_link_2

    FROM enriched_jobs j
    LEFT JOIN companies c ON j.company_name = c.company_name
)

select * from final