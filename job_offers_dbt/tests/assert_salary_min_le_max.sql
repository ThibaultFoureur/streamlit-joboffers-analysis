-- tests/assert_salary_min_le_max.sql

{{ config(
    severity = 'warn',
    description = 'Check if min salary exceeds max salary, failing only if more than 2% of records are affected.'
) }}

WITH all_records AS (
    SELECT job_id, annual_min_salary, annual_max_salary
    FROM {{ ref('int_jobs_enriched') }}
    -- We only care about records where both salaries are present
    WHERE annual_min_salary IS NOT NULL AND annual_max_salary IS NOT NULL
),

validation_errors AS (
    SELECT *
    FROM all_records
    WHERE annual_min_salary > annual_max_salary
),

test_summary AS (
    SELECT
        (SELECT COUNT(*) FROM validation_errors) AS error_count,
        (SELECT COUNT(*) FROM all_records) AS total_count
)

-- The test returns rows ONLY if the percentage threshold is breached
SELECT
    v.*
FROM validation_errors v
CROSS JOIN test_summary s
WHERE (s.error_count::FLOAT / NULLIF(s.total_count, 0)) > 0.02 