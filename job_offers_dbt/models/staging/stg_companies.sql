-- This model cleans and prepares the raw company data, extracting key fields from the company_info JSON blob.
with source as (

    select * from {{ source('public', 'raw_companies') }}

),

extracted_and_renamed as (

    select
        -- The original company name from the job offer
        company_name,

        -- Extract specific fields from the raw JSONB column
        -- The ->> operator extracts a JSON object field as text.
        company_info ->> 'section_activite_principale' as activity_section_code,
        company_info ->> 'activite_principale' as main_activity_code,
        company_info ->> 'categorie_entreprise' as company_category,
        company_info ->> 'tranche_effectif_salarie' as employee_range,
        
        -- Keep the raw JSON for auditing or future use
        company_info,
        created_at

    from source

),

final as (

    select
        *,

        -- Map the activity section code to a human-readable description
        CASE activity_section_code
            WHEN 'A' THEN 'Agriculture, forestry and fishing'
            WHEN 'B' THEN 'Mining and quarrying'
            WHEN 'C' THEN 'Manufacturing'
            WHEN 'D' THEN 'Electricity, gas, steam and air conditioning supply'
            WHEN 'E' THEN 'Water supply; sewerage, waste management and remediation activities'
            WHEN 'F' THEN 'Construction'
            WHEN 'G' THEN 'Wholesale and retail trade; repair of motor vehicles and motorcycles'
            WHEN 'H' THEN 'Transportation and storage'
            WHEN 'I' THEN 'Accommodation and food service activities'
            WHEN 'J' THEN 'Information and communication'
            WHEN 'K' THEN 'Financial and insurance activities'
            WHEN 'L' THEN 'Real estate activities'
            WHEN 'M' THEN 'Professional, scientific and technical activities'
            WHEN 'N' THEN 'Administrative and support service activities'
            WHEN 'O' THEN 'Public administration and defence; compulsory social security'
            WHEN 'P' THEN 'Education'
            WHEN 'Q' THEN 'Human health and social work activities'
            WHEN 'R' THEN 'Arts, entertainment and recreation'
            WHEN 'S' THEN 'Other service activities'
            WHEN 'T' THEN 'Activities of households as employers; undifferentiated goods- and services-producing activities of households for own use'
            WHEN 'U' THEN 'Activities of extraterritorial organisations and bodies'
            ELSE 'Not specified'
        END as activity_section_details,

        -- Flag companies based on their main activity code (APE code)
        CASE
            WHEN main_activity_code IN ('62.02A', '70.22Z', '7021Z') THEN TRUE
            ELSE FALSE
        END as is_consulting_company

    from extracted_and_renamed
)

select * from final