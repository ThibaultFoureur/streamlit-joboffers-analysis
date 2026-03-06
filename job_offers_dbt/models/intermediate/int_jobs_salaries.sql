WITH jobs AS (
    SELECT 
        job_id, 
        raw_salary 
    FROM {{ ref('stg_jobs') }}
    WHERE raw_salary IS NOT NULL
),

salary_calculations AS (

    SELECT
        job_id,
        raw_salary,

        -- 1. Standardize string for parsing
        LOWER(REPLACE(REPLACE(REPLACE(raw_salary, ',', '.'), ' ', ''), '€', '')) AS salary,

        -- 2. Determine the multiplier based on the period (day, month, year)
        CASE
            WHEN raw_salary ILIKE '%par jour%' OR raw_salary ILIKE '%per day%' THEN 220 -- Assuming ~220 working days/year
            WHEN raw_salary ILIKE '%par mois%' OR raw_salary ILIKE '%per month%' THEN 12
            ELSE 1
        END AS multiplier,

        -- 3. Extract numeric values using REGEX, keeping only digits and the decimal point
        -- Use NULLIF to handle cases where no numbers are found, preventing errors
        NULLIF(REGEXP_REPLACE(
            REPLACE(
                CASE
                        -- If there's a range (using 'à'), take the first part
                        WHEN raw_salary LIKE '%à%' THEN SPLIT_PART(LOWER(raw_salary), 'à', 1)
                        ELSE raw_salary
                    END,
                ',', '.'),
        '[^0-9.]', '', 'g'), '')::NUMERIC AS min_value,

        NULLIF(REGEXP_REPLACE(
            CASE
                -- If there's a range, take the second part
                WHEN raw_salary LIKE '%à%' THEN SPLIT_PART(LOWER(raw_salary), 'à', 2)
                -- Otherwise, it's a single value, so max is same as min
                ELSE raw_salary
            END,
        '[^0-9.]', '', 'g'), '')::NUMERIC AS max_value,

        -- 4. Check if the raw_salary was mentioned in thousands ('k')
        CASE WHEN raw_salary LIKE '%k%' THEN 1000 ELSE 1 END AS k_multiplier

    FROM jobs

),

annual_salary AS (

    SELECT
        job_id,
        salary,
        -- 5. Calculate the final annual raw_salary, including a heuristic for cases where 'k' was likely omitted
        CASE
            -- If the calculated yearly raw_salary is less than 1000, it's likely the 'k' was missing
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
)

SELECT 
    job_id,
    salary,
    annual_min_salary,
    annual_max_salary
FROM annual_salary