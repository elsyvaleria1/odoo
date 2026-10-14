from odoo.tools.module_data import rename_field, rename_model, rename_xmlids


def migrate(cr, version):
    rename_model(cr, "agent.capability", "runner.capability")
    rename_model(cr, "agent.runner", "runner.machine")
    rename_model(cr, "agent.run", "runner.job")
    rename_model(cr, "agent.run.event", "runner.job.event")
    rename_field(cr, "runner.job", "runner_id", "machine_id")
    rename_field(cr, "runner.job", "run_state", "job_state")
    rename_field(cr, "runner.job.event", "run_id", "job_id")
    rename_field(cr, "runner.machine", "run_ids", "job_ids")
    rename_xmlids(
        cr,
        "runner",
        {
            "access_agent_capability_system": "access_runner_capability_system",
            "access_agent_run_event_system": "access_runner_job_event_system",
            "access_agent_run_system": "access_runner_job_system",
            "access_agent_runner_system": "access_runner_machine_system",
            "action_agent_run": "action_runner_job",
            "action_agent_runner": "action_runner_machine",
            "menu_agent_run": "menu_runner_job",
            "menu_agent_runner": "menu_runner_machine",
            "menu_agent_runner_root": "menu_runner_root",
            "privilege_run_agent": "privilege_runner",
            "privilege_run_agent_capability": "privilege_runner_capability",
            "privilege_run_agent_event": "privilege_runner_job_event",
            "privilege_run_agent_run_read": "privilege_runner_job_read",
            "privilege_run_agent_run_write": "privilege_runner_job_write",
            "privilege_run_agent_runner": "privilege_runner_machine",
            "user_agent_runner": "user_runner",
            "user_agent_runner_res_partner": "user_runner_res_partner",
            "view_agent_run_form": "view_runner_job_form",
            "view_agent_run_list": "view_runner_job_list",
            "view_agent_run_search": "view_runner_job_search",
            "view_agent_runner_form": "view_runner_machine_form",
            "view_agent_runner_list": "view_runner_machine_list",
        },
    )
    cr.execute(
        "UPDATE res_users SET login = '__runner__' WHERE login = '__agent_runner__'"
    )
