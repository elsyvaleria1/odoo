from odoo.tools.module_data import rename_module


def migrate(cr, version):
    if not version:
        return
    rename_module(cr, "agent_runner_github", "runner_github")
    rename_module(cr, "agent_runner", "runner")
