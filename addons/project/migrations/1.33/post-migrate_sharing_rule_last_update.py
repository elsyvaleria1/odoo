import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    # the record is noupdate: the data file no longer switching it off reaches
    # an existing database only through this write
    rule = env.ref(
        "project.project_task_rule_portal_project_sharing", raise_if_not_found=False
    )
    if rule and not rule.active:
        rule.active = True
        _logger.info("project: portal project sharing rule activated")
    projects = env["project.project"].with_context(active_test=False).search([])
    projects.modified(["update_ids"])
    env.flush_all()
    _logger.info("project: last update recomputed on %s projects", len(projects))
