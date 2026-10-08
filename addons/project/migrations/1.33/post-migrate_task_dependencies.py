import logging

from odoo import SUPERUSER_ID, api
from odoo.db import schema

_logger = logging.getLogger(__name__)

# predecessor_ids and successor_ids read project_task_dependency, the typed rows,
# instead of a relation of their own; a link only the old relation held becomes
# a finish-to-start row without lag, and the relation goes with its reflection.
# Blocking now reads the type (a finish-to-finish predecessor no longer blocks
# the start), so every task with a dependency has its state recomputed


def migrate(cr, version):
    if not version:
        return
    if schema.table_exists(cr, "project_task_dependency_rel"):
        cr.execute(
            """
            INSERT INTO project_task_dependency
                   (task_id, depends_on_id, dependency_type, lag_hours,
                    create_date, write_date)
            SELECT rel.task_id, rel.depends_on_id, 'fs', 0,
                   now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC'
              FROM project_task_dependency_rel rel
             WHERE rel.task_id != rel.depends_on_id
                ON CONFLICT (task_id, depends_on_id) DO NOTHING
            """
        )
        _logger.info("project: %s dependency links became typed rows", cr.rowcount)
        cr.execute("DROP TABLE project_task_dependency_rel")
        cr.execute(
            "DELETE FROM ir_model_relation WHERE name = 'project_task_dependency_rel'"
        )
    cr.execute("SELECT DISTINCT task_id FROM project_task_dependency")
    tasks = api.Environment(cr, SUPERUSER_ID, {})["project.task"].browse(
        [task_id for (task_id,) in cr.fetchall()]
    )
    tasks.modified(["dependency_ids"])
    tasks.env.flush_all()
    _logger.info("project: blocking re-read by type on %s tasks", len(tasks))
