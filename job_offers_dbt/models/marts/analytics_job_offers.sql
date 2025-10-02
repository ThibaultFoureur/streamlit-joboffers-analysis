-- This is the final model, ready for analysis and for the Streamlit app.

with joined as (

    select * from {{ ref('int_jobs_with_companies') }}

),

final as (

    select
        -- Select and reorder the final columns
        title,
        company_name,
        company_category,
        activity_section_details,
        location,
        via,
        salary is not null as is_salary_mentioned, -- Business logic moved to dbt
        salary,
        annual_min_salary,
        annual_max_salary,
        work_titles_final,
        schedule_type,
        posted_at,
        seniority_category,
        languages,
        bi_tools,
        cloud_platforms,
        data_modelization,

        -- Final business logic for consulting status
        CASE
            WHEN lower(title) ILIKE '%consult%' THEN 'Consulting'
            WHEN (lower(title) ILIKE ANY (ARRAY['%consultant%', '%consulting%'])) AND is_consulting_company THEN 'Consulting'
            WHEN (lower(title) ILIKE ANY (ARRAY['%consultant%', '%consulting%'])) OR is_consulting_company THEN 'Probably consulting'
            ELSE 'Internal position'
        END as consulting_status,

        -- Keep IDs and useful text fields at the end
        description,
        full_text,
        job_id,
        apply_link_1,
        apply_link_2

    from joined
)

select * from final