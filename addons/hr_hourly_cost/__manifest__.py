{
    "name": "Employee Hourly Cost",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Services/Timesheets",
    "summary": "Store employee hourly costs for use by time-valuation modules",
    "description": "Adds a nonnegative monetary hourly cost visible to HR users and its employee form field. Converts existing costs when the employee changes company currency unless a new cost is supplied; downstream modules must implement the valuation of worked time.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "hr",
    ],
    "data": [
        "views/hr_employee_views.xml",
    ],
    "demo": [
        "demo/hr_hourly_cost_demo.xml",
    ],
}
