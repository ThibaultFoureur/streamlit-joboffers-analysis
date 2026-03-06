WITH source AS (
    SELECT * FROM {{ source('public', 'raw_jobs') }}
),

renamed AS (
    SELECT
        job_id,
        title,
        company_name,
        location,
        description,
        via,
        created_at,
        detected_extensions ->> 'posted_at' AS raw_posted_at,
        detected_extensions ->> 'salary' AS raw_salary,
        detected_extensions ->> 'schedule_type' AS raw_schedule_type,
        apply_options -> 0 ->> 'link' AS apply_link_1,
        apply_options -> 1 ->> 'link' AS apply_link_2
    FROM source
)

SELECT * FROM renamed