from odoo.tools.module_data import rename_xmlids


def migrate(cr, version):
    rename_xmlids(
        cr,
        "error_incident_autofix",
        {
            "privilege_report_agent_run": "privilege_report_runner_job",
            "privilege_report_agent_run_incident": "privilege_report_runner_job_incident",
            "privilege_report_agent_run_occurrence": (
                "privilege_report_runner_job_occurrence"
            ),
            "privilege_report_agent_run_policy": "privilege_report_runner_job_policy",
            "privilege_report_agent_run_prompt": "privilege_report_runner_job_prompt",
            "privilege_report_agent_run_pull": "privilege_report_runner_job_pull",
            "privilege_report_agent_run_repository": (
                "privilege_report_runner_job_repository"
            ),
            "privilege_report_agent_run_run": "privilege_report_runner_job_job",
        },
    )
