-- This model cleans and casts the raw user configuration data
WITH source AS (
    SELECT * FROM {{ source('public', 'user_configs') }}
),

renamed AS (
    SELECT
        -- Casting user_id to UUID for consistent joining
        CAST(user_id AS UUID) AS user_id,
        
        -- Search parameters
        search_queries,
        LOWER(search_location) AS search_location,
        
        -- Keeping JSONB as is for unnesting in Intermediate layer
        search_skills,
        
        -- Metadata
        CAST(updated_at AS TIMESTAMPTZ) AS updated_at
    FROM source
)

SELECT * FROM renamed