import logging

from odoo import SUPERUSER_ID, api
from odoo.tools import parse_version

_logger = logging.getLogger(__name__)

# The rule is noupdate: the data file no longer switching it off reaches an
# existing database only through this write, and only on one whose last loaded
# code still toggled it. That is every 1.31, but 1.32 shipped both with the
# toggle (f783acac189b) and without it (41bf38ea8c56), where a rule found off
# was turned off by an admin. The version cannot tell them apart; the group
# 41bf38ea8c56 removed can: its xmlid is still there, until this upgrade ends,
# only on a database that never loaded code past the toggle
TOGGLE_ERA_XMLID = ("project", "privilege_manage_feature_groups")


def _is_from_toggle_era(cr, version):
    if parse_version(version) < parse_version("19.0.1.32"):
        return True
    cr.execute(
        "SELECT 1 FROM ir_model_data WHERE module = %s AND name = %s",
        list(TOGGLE_ERA_XMLID),
    )
    return cr.fetchone() is not None


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    rule = env.ref(
        "project.project_task_rule_portal_project_sharing", raise_if_not_found=False
    )
    if rule and not rule.active:
        if _is_from_toggle_era(cr, version):
            rule.active = True
            _logger.info("project: portal project sharing rule activated")
        else:
            _logger.info(
                "project: portal project sharing rule left inactive: it was "
                "turned off after it stopped being toggled"
            )
    projects = env["project.project"].with_context(active_test=False).search([])
    projects.modified(["update_ids"])
    env.flush_all()
    _logger.info("project: last update recomputed on %s projects", len(projects))
