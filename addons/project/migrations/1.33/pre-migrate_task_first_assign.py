import logging

from odoo.db import schema

_logger = logging.getLogger(__name__)



def migrate(cr, version):
    if not version or schema.column_exists(cr, "project_task", "date_first_assign"):
        return
    schema.create_column(cr, "project_task", "date_first_assign", "timestamp")
    cr.execute(
        """
        UPDATE project_task t
           SET date_first_assign = COALESCE(t.date_assign, t.create_date)
         WHERE t.date_assign IS NOT NULL
            OR EXISTS (SELECT 1 FROM project_task_user_rel r WHERE r.task_id = t.id)
        """
    )
    _logger.info("project: %s first assignment dates backfilled", cr.rowcount)
