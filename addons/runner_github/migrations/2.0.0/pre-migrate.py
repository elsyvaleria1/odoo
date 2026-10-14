from odoo.tools.module_data import rename_field, rename_xmlids


def migrate(cr, version):
    rename_field(cr, "integration.github.pull", "agent_run_id", "runner_job_id")
    rename_xmlids(
        cr,
        "runner_github",
        {"view_agent_run_form_github": "view_runner_job_form_github"},
    )
