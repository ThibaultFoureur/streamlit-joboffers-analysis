WITH jobs AS (
    SELECT 
        job_id, 
        created_at, 
        raw_posted_at 
    FROM {{ ref('stg_jobs') }}
),

parsed_dates AS (
    SELECT
        job_id,
        CASE
            -- 1. If posted_at is NULL or empty, fallback to created_at
            WHEN raw_posted_at IS NULL 
            OR raw_posted_at = '' THEN created_at

            -- 2. Handle "X hours ago" (heures)
            WHEN raw_posted_at ~ 'il y a \d+ heure' THEN
                created_at - (
                    (REGEXP_MATCH(raw_posted_at, 'il y a (\d+) heure'))[1] || ' hours'
                )::INTERVAL

            -- 3. Handle "X days ago" (jours)
            WHEN raw_posted_at ~ 'il y a \d+ jour' THEN
                created_at - (
                    (REGEXP_MATCH(raw_posted_at, 'il y a (\d+) jour'))[1] || ' days'
                )::INTERVAL

            -- 4. Handle "X minutes ago" (minutes) - just in case
            WHEN raw_posted_at ~ 'il y a \d+ minute' THEN
                created_at - (
                    (REGEXP_MATCH(raw_posted_at, 'il y a (\d+) minute'))[1] || ' minutes'
                )::INTERVAL

            -- 5. Handle "X months ago" (mois)
            WHEN raw_posted_at ~ 'il y a \d+ mois' THEN
                created_at - (
                    (REGEXP_MATCH(raw_posted_at, 'il y a (\d+) mois'))[1] || ' months'
                )::INTERVAL
                
            -- Default fallback if the format is unrecognized
            ELSE created_at
        END AS posted_at
    FROM jobs
)

SELECT * FROM parsed_dates