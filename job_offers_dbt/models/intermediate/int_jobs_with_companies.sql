-- This model joins the staged jobs data with the staged companies data.

with jobs as (

    select * from {{ ref('stg_jobs') }}

),

companies as (

    select * from {{ ref('stg_companies') }}

),

final as (
    
    select
        -- All columns from the jobs model
        jobs.*,

        -- All columns from the companies model, excluding the join key
        companies.company_category,
        companies.employee_range,
        companies.activity_section_details,
        companies.is_consulting_company

    from jobs

    left join companies
        on jobs.company_name = companies.company_name
)

select * from final