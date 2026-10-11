import binascii
from urllib.parse import urlencode

from odoo.exceptions import AccessError, MissingError
from odoo.http import request, route
from odoo.libs.debug_log import DebugLog

from odoo.addons.base.models.access_link import ROLE_RANK
from odoo.addons.portal.controllers import portal
from odoo.addons.portal.utils import get_url_with_params, thread_link

_debug = DebugLog(__name__)

WORKSHEET_SOURCES = frozenset({"fsm", "project"})


class CustomerPortal(portal.CustomerPortal):
    def _prepare_worksheet_context(self, task_sudo):
        return {}

    def _task_get_page_view_values(self, task, access_token, /, **kwargs):
        values = super()._task_get_page_view_values(task, access_token, **kwargs)
        values["source"] = self._get_worksheet_source(task, kwargs.get("source"))
        values["worksheet_sign_url"] = self._get_worksheet_sign_url(task, values)
        return values

    def _get_worksheet_sign_url(self, task, values):
        url = f"{task.access_url}/worksheet/sign/{values['source']}"
        token = values.get("task_token")
        if not token:
            return url
        link = getattr(request, "access_link", None)
        own_link = bool(link) and link.res_model == task._name
        if own_link:
            signs = ROLE_RANK[link.role] >= ROLE_RANK[
                "comment"
            ] and self._signs_for_customer(task, link.partner_id)
            params = {"access_token": token}
        else:
            pid = values.get("pid")
            signs = bool(pid and values.get("hash")) and self._signs_for_customer(
                task, task.env["res.partner"].browse(int(pid))
            )
            params = {"access_token": token, "pid": pid, "hash": values.get("hash")}
        _debug.logic(
            "worksheet_sign_offered",
            task=task.id,
            by="task_link" if own_link else "project_link",
            signs=signs,
        )
        return get_url_with_params(url, params) if signs else None

    @staticmethod
    def _signs_for_customer(task_sudo, partner):
        partner = task_sudo.env["res.partner"].browse(partner.id if partner else [])
        customer = task_sudo.partner_id.commercial_partner_id
        signs = bool(customer and partner) and (
            partner.commercial_partner_id == customer
        )
        _debug.logic(
            "worksheet_signer",
            task=task_sudo.id,
            partner=partner.id if partner else None,
            customer=customer.id,
            signs=signs,
        )
        return signs

    @staticmethod
    def _get_worksheet_source(task, source):
        if source in WORKSHEET_SOURCES:
            return source
        return "fsm" if task.is_fsm else "project"

    @route(
        [
            "/my/task/<int:task_id>/worksheet",
            "/my/task/<int:task_id>/worksheet/<string:source>",
            "/my/task/<int:task_id>/worksheet/sign/<string:source>",
        ],
        type="http",
        auth="public",
    )
    def portal_worksheet_outdated(self, **kwargs):
        return request.redirect(
            request.httprequest.path.replace("/my/task/", "/my/tasks/")
        )

    @route(
        ["/my/tasks/<int:task_id>/worksheet/sign/<string:source>"],
        type="jsonrpc",
        auth="public",
        website=True,
    )
    def portal_worksheet_sign(
        self, task_id, access_token=None, source=False, name=None, signature=None
    ):
        query = request.httprequest.args
        access_token = access_token or query.get("access_token")
        by_project_link = False
        try:
            task_sudo = request.env["access.link"]._open_record(
                "project.task", task_id, access_token=access_token, role="comment"
            )
        except MissingError:
            return {"error": request.env._("Invalid Task.")}
        except AccessError:
            task_sudo = self._open_task_by_project_link(
                task_id, access_token, query.get("pid"), query.get("hash")
            )
            if not task_sudo:
                return {"error": request.env._("Invalid Task.")}
            by_project_link = True
            signer = task_sudo.env["res.partner"].browse(int(query["pid"]))
        else:
            signer = (
                None
                if task_sudo.with_user(request.env.user).has_access("read")
                else thread_link(task_sudo, access_token, role="comment").partner_id
            )
        if signer is not None and not self._signs_for_customer(task_sudo, signer):
            return {"error": request.env._("Invalid Task.")}

        if not task_sudo._has_to_be_signed():
            return {
                "error": request.env._(
                    "The worksheet is not in a state requiring customer signature."
                )
            }
        if not signature:
            return {"error": request.env._("Signature is missing.")}

        try:
            task_sudo.write(
                {
                    "worksheet_signature": signature,
                    "worksheet_signed_by": name,
                }
            )
        except TypeError, binascii.Error:
            return {"error": request.env._("Invalid signature data.")}

        pdf = (
            request.env["ir.actions.report"]
            .sudo()
            ._render_qweb_pdf("industry_fsm.task_custom_report", [task_sudo.id])[0]
        )
        task_sudo.message_post(
            body=request.env._(
                "The field service report has been signed by the customer."
            ),
            attachments=[
                (
                    "Field Service Report - %s - %s.pdf"
                    % (task_sudo.name, task_sudo.partner_id.name),
                    pdf,
                )
            ],
        )
        source = self._get_worksheet_source(task_sudo, source)
        _debug.lifecycle(
            "worksheet_signed", task=task_sudo.id, by_project_link=by_project_link
        )
        if by_project_link:
            redirect_url = get_url_with_params(
                f"{task_sudo.project_id.access_url}/task/{task_sudo.id}",
                {"access_token": access_token, "source": source},
            )
        else:
            redirect_url = task_sudo.get_portal_url(
                query_string=f"&{urlencode({'source': source})}"
            )
        return {"force_refresh": True, "redirect_url": redirect_url}

    def _show_task_report(self, task_sudo, report_type, download):
        if not task_sudo.is_fsm:
            return super()._show_task_report(task_sudo, report_type, download)
        return self._show_report(
            model=task_sudo,
            report_type=report_type,
            report_ref="industry_fsm.task_custom_report",
            download=download,
        )
