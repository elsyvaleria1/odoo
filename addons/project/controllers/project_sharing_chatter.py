from werkzeug.exceptions import Forbidden

from odoo.http import request
from odoo.libs.debug_log import DebugLog

from odoo.addons.portal.controllers.portal_thread import PortalChatter

_debug = DebugLog(__name__)


class ProjectSharingChatter(PortalChatter):
    def _get_task_post_token(
        self, project_id: int, res_model: str, res_id: int, token: str | None
    ) -> str:
        project_sudo = request.env["access.link"]._open_record(
            "project.project", project_id, token
        )
        can_access = (
            project_sudo
            and res_model == "project.task"
            and project_sudo.with_user(
                request.env.user
            )._is_project_sharing_accessible()
        )
        task = None
        if can_access:
            task = (
                request.env["project.task"]
                .sudo()
                .with_context(active_test=False)
                .search([("id", "=", res_id), ("project_id", "=", project_sudo.id)])
            )
        _debug.logic(
            "sharing_chatter_access",
            project=project_id,
            res_model=res_model,
            res_id=res_id,
            uid=request.env.uid,
            can_access=bool(can_access),
            task=task and task.id,
        )
        if not can_access or not task:
            raise Forbidden
        return task[task._mail_post_token_field]
