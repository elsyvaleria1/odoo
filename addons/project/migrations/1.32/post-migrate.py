from odoo.tools import SQL

REMOVED_MODELS = ("wizard.project.phase.delete", "wizard.project.workflow.step.delete")
REMOVED_TABLES = (
    "project_phase_wizard_project_phase_delete_rel",
    "project_project_wizard_project_workflow_step_delete_rel",
    "project_workflow_step_wizard_project_workflow_step_delete_rel",
    "wizard_project_phase_delete",
    "wizard_project_workflow_step_delete",
)


def migrate(cr, version):
    if not version:
        return
    for table in REMOVED_TABLES:
        cr.execute(SQL("DROP TABLE IF EXISTS %s", SQL.identifier(table)))
    cr.execute(SQL("DELETE FROM ir_model WHERE model = ANY(%s)", list(REMOVED_MODELS)))
