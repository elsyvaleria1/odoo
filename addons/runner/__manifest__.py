{
    "name": "Runners",
    "version": "19.0.2.0.0",
    "category": "Hidden/Tools",
    "summary": "Hand work to isolated runner machines over a leased, authenticated protocol",
    "description": "Queues jobs and leases each to exactly one runner machine with the capability it needs. A runner authenticates with its own token, claims a job, keeps its lease alive, reports events and finishes it; an expired lease is handed out again within a bounded number of attempts. Reported spend counts against the company's machine-learning budget, and a company over budget is handed no work.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "integration_machine_learning",
        "mail",
    ],
    "data": [
        "security/res_groups.xml",
        "security/ir.access.csv",
        "data/runner_capability_data.xml",
        "data/res_users_data.xml",
        "data/ir_cron.xml",
        "views/runner_machine_views.xml",
        "views/runner_job_views.xml",
        "views/runner_menus.xml",
    ],
}
