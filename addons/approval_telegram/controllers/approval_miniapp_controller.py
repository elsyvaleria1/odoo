import base64
import logging

from odoo import fields, http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.libs.json import dumps as json_dumps

from odoo.addons.telegram.tools import format as tg
from odoo.addons.telegram.tools.dispatch import translation_env

_logger = logging.getLogger(__name__)

_MAX_PANEL_LINES = 200


class ApprovalMiniAppController(http.Controller):
    @http.route(
        "/telegram/approval/app/<int:bot_id>",
        type="http",
        auth="public",
    )
    def approval_miniapp(self, bot_id, **kwargs):
        bot = request.env["telegram.bot"].browse(bot_id).exists()
        if not bot:
            raise request.prepare_not_found_error()
        html = request.env["ir.qweb"]._render(
            "approval_telegram.miniapp_page", {"bot_id": bot_id}
        )
        return request.prepare_response(
            "<!DOCTYPE html>\n" + str(html),
            headers=[("Content-Type", "text/html; charset=utf-8")],
        )

    @http.route(
        "/telegram/approval/app/<int:bot_id>/pending",
        type="http",
        auth="receiver",
        receiver="telegram.bot:_receiver_for_mini_app",
        receiver_event="mini_app",
        receiver_refusal="telegram.bot:_prepare_mini_app_refusal_response",
        methods=["POST"],
        csrf=False,
        typed=True,
    )
    def approval_miniapp_pending(self, bot_id: int, **kwargs):
        bot, user, telegram_user_id = self._caller()
        labels = self._labels(bot, user)
        if not user:
            return self._json({"ok": False, "error": "unlinked", "labels": labels})
        domain = [
            ("user_id", "=", user.id),
            ("state", "in", ("pending", "waiting", "approved", "refused")),
        ]
        try:
            request_id = int(kwargs.get("request_id") or 0)
        except ValueError:
            request_id = 0
        if request_id:
            domain.append(("request_id", "=", request_id))
        approvers = (
            request.env["approval.approver"]
            .with_user(user)
            .search(domain, order="id desc", limit=40)
        )
        payload = [self._approver_payload(approver, user) for approver in approvers]
        return self._json(
            {
                "ok": True,
                "requests": payload,
                "labels": labels,
                "session": bot._mint_mini_app_session(telegram_user_id),
            }
        )

    @http.route(
        "/telegram/approval/app/<int:bot_id>/act",
        type="http",
        auth="receiver",
        receiver="telegram.bot:_receiver_for_mini_app",
        receiver_event="mini_app",
        receiver_refusal="telegram.bot:_prepare_mini_app_refusal_response",
        methods=["POST"],
        csrf=False,
        typed=True,
    )
    def approval_miniapp_act(self, bot_id: int, **kwargs):
        approver, error = self._resolve_act_approver(kwargs.get("approver_id"))
        if error:
            return self._json({"ok": False, "error": error})
        notifier = request.env["telegram.approval.notifier"]
        action = kwargs.get("action")
        note = (kwargs.get("note") or "").strip() or None
        field = kwargs.get("field")
        if action not in ("approve", "refuse", "change"):
            return self._json({"ok": False, "error": "bad_action"})
        if action == "change" and field not in ("date", "reason"):
            return self._json({"ok": False, "error": "bad_field"})
        try:
            with request.env.cr.savepoint():
                if action == "approve":
                    notifier._approve(approver)
                elif action == "refuse":
                    reason_id = int(kwargs.get("reason_id") or 0) or None
                    notifier._refuse(approver, reason_id=reason_id, note=note)
                else:
                    notifier._request_change(approver, field, note=note)
        except UserError as exc:
            return self._json({"ok": False, "error": str(exc)})
        return self._json({"ok": True})

    def _resolve_act_approver(self, approver_id_raw):
        empty = request.env["approval.approver"].browse()
        _bot, user, _telegram_user_id = self._caller()
        if not user:
            return empty, "unlinked"
        try:
            approver_id = int(approver_id_raw or 0)
        except ValueError:
            return empty, "bad"
        approver = (
            request.env["approval.approver"]
            .with_user(user)
            .search([("id", "=", approver_id)])
        )
        if (
            not approver
            or approver.state != "pending"
            or approver._get_effective_approver() != user
        ):
            return empty, "not_pending"
        return approver.with_context(lang=user.lang), None

    @http.route(
        "/telegram/approval/app/<int:bot_id>/attachment/<int:attachment_id>",
        type="http",
        auth="receiver",
        receiver="telegram.bot:_receiver_for_mini_app",
        receiver_event="mini_app",
        receiver_refusal="telegram.bot:_prepare_mini_app_refusal_response",
        methods=["GET"],
        typed=True,
    )
    def approval_miniapp_attachment(self, bot_id: int, attachment_id: int, **kwargs):
        _bot, user, _telegram_user_id = self._caller()
        if not user:
            raise request.prepare_not_found_error()
        attachment = (
            request.env["ir.attachment"]
            .with_user(user)
            .search(
                [("id", "=", attachment_id), ("res_model", "=", "approval.request")]
            )
        )
        if not attachment:
            raise request.prepare_not_found_error()
        is_approver = (
            request.env["approval.approver"]
            .with_user(user)
            .search_count(
                [
                    ("user_id", "=", user.id),
                    ("request_id", "=", attachment.res_id),
                ]
            )
        )
        if not is_approver:
            raise request.prepare_not_found_error()
        return request.prepare_response(
            base64.b64decode(attachment.datas or b""),
            headers=[
                ("Content-Type", attachment.mimetype or "application/octet-stream"),
                (
                    "Content-Disposition",
                    f'inline; filename="{attachment.name or "attachment"}"',
                ),
            ],
        )

    @http.route(
        "/telegram/approval/app/<int:bot_id>/fix/<int:request_id>",
        type="http",
        auth="public",
    )
    def approval_miniapp_fix(self, bot_id, request_id, **kwargs):
        bot = request.env["telegram.bot"].browse(bot_id).exists()
        if not bot:
            raise request.prepare_not_found_error()
        html = request.env["ir.qweb"]._render(
            "approval_telegram.fix_page",
            {"bot_id": bot_id, "request_id": request_id},
        )
        return request.prepare_response(
            "<!DOCTYPE html>\n" + str(html),
            headers=[("Content-Type", "text/html; charset=utf-8")],
        )

    @http.route(
        "/telegram/approval/app/<int:bot_id>/fix/<int:request_id>/data",
        type="http",
        auth="receiver",
        receiver="telegram.bot:_receiver_for_mini_app",
        receiver_event="mini_app",
        receiver_refusal="telegram.bot:_prepare_mini_app_refusal_response",
        methods=["POST"],
        csrf=False,
        typed=True,
    )
    def approval_miniapp_fix_data(self, bot_id: int, request_id: int, **kwargs):
        owner_request, session, error = self._resolve_owner_request(
            bot_id, request_id, kwargs
        )
        bot, user, _telegram_user_id = self._caller()
        labels = self._labels(bot, user)
        if error:
            return self._json({"ok": False, "error": error, "labels": labels})
        field = owner_request.pending_change_field
        if field == "date":
            value = (
                fields.Date.to_string(owner_request.date.date())
                if owner_request.date
                else ""
            )
        else:
            value = owner_request.reason or ""
        return self._json(
            {
                "ok": True,
                "field": field,
                "value": value,
                "name": owner_request.name,
                "comment": owner_request.tg_change_note or "",
                "labels": labels,
                "session": session,
            }
        )

    @http.route(
        "/telegram/approval/app/<int:bot_id>/fix/<int:request_id>/save",
        type="http",
        auth="receiver",
        receiver="telegram.bot:_receiver_for_mini_app",
        receiver_event="mini_app",
        receiver_refusal="telegram.bot:_prepare_mini_app_refusal_response",
        methods=["POST"],
        csrf=False,
        typed=True,
    )
    def approval_miniapp_fix_save(self, bot_id: int, request_id: int, **kwargs):
        owner_request, _session, error = self._resolve_owner_request(
            bot_id, request_id, kwargs
        )
        if error:
            return self._json({"ok": False, "error": error})
        notifier = request.env["telegram.approval.notifier"]
        value = (kwargs.get("value") or "").strip()
        try:
            with request.env.cr.savepoint():
                applied = notifier._apply_owner_fix(owner_request, value)
        except UserError as exc:
            return self._json({"ok": False, "error": str(exc)})
        if not applied:
            return self._json(
                {"ok": False, "error": owner_request.env._("Invalid date.")}
            )
        chat = notifier._target_chat(
            owner_request.request_owner_id, owner_request.company_id
        )
        if chat:
            chat.bot_id.send_message(
                chat.chat_id,
                translation_env(chat.bot_id, chat)._(
                    "✅ Correction sent. %(request)s is back in approval."
                )
                % {"request": tg.escape(owner_request.name)},
            )
        return self._json({"ok": True})

    def _resolve_owner_request(self, bot_id, request_id, kwargs):
        empty = request.env["approval.request"].browse()
        bot, user, telegram_user_id = self._caller()
        if not user:
            return empty, None, "unlinked"
        approval_request = (
            request.env["approval.request"]
            .with_user(user)
            .with_context(lang=user.lang)
            .search([("id", "=", request_id)])
        )
        if (
            approval_request.request_owner_id != user
            or not approval_request.pending_change_field
        ):
            return empty, None, "not_owner"
        return approval_request, bot._mint_mini_app_session(telegram_user_id), None

    @staticmethod
    def _json(data):
        return request.prepare_response(
            json_dumps(data),
            headers=[("Content-Type", "application/json")],
        )

    @staticmethod
    def _caller():
        admission = request.admission
        bot = admission.subject
        telegram_user_id = admission.extra["telegram_user_id"]
        return bot, bot._mini_app_user(telegram_user_id), telegram_user_id

    @staticmethod
    def _labels(bot, user):
        return (
            request.env["telegram.approval.notifier"]
            .with_context(lang=user.lang if user else bot.get_lang())
            ._mini_app_labels()
        )

    @staticmethod
    def _approver_payload(approver, user):
        req = approver.request_id
        can_act = bool(
            approver.state == "pending"
            and req.state == "pending"
            and not req.pending_change_field
            and approver._get_effective_approver() == user
        )

        def fmt_date(value):
            return fields.Date.to_string(value.date()) if value else ""

        journal = ""
        if "journal_id" in req._fields and req.journal_id:
            journal = req.journal_id.display_name or ""

        detail = ApprovalMiniAppController._lines_payload(req)

        payload = {
            "approver_id": approver.id,
            "approver_state": approver.state,
            "can_act": can_act,
            "id": req.id,
            "name": req.name,
            "state": req.state,
            "category": req.category_id.name or "",
            "owner": req.request_owner_id.name or "",
            "amount": req.amount or 0.0,
            "currency": req.company_id.currency_id.symbol or "",
            "quantity": req.quantity or 0.0,
            "partner": req.partner_id.name or "",
            "reference": req.reference or "",
            "location": req.location or "",
            "priority": req.priority or "0",
            "journal": journal,
            "date": fmt_date(req.date),
            "date_start": fmt_date(req.date_start),
            "date_end": fmt_date(req.date_end),
            "date_deadline": fmt_date(req.date_deadline),
            "reason": "" if detail["live"] else (req.reason or ""),
            "lines": detail["lines"],
            "lines_more": detail["more"],
            "lines_source": detail["source"],
            "approvers": [
                {
                    "name": item._get_effective_approver().name or "",
                    "state": item.state,
                }
                for item in req.approver_ids.sorted("sequence")
            ],
            "attachments": [
                {
                    "id": att.id,
                    "name": att.name or "",
                    "mimetype": att.mimetype or "",
                    "is_image": (att.mimetype or "").startswith("image/"),
                }
                for att in req.attachment_ids
            ],
            "reasons": [],
        }
        if can_act:
            payload["reasons"] = ApprovalMiniAppController._reasons_payload(
                req.category_id
            )
        return payload

    @staticmethod
    def _lines_payload(req):
        lines = [
            {
                "product": line.product_id.display_name or "",
                "description": line.description or "",
                "quantity": line.quantity,
                "price_unit": line.price_unit,
            }
            for line in req.line_ids
        ]
        if lines or not hasattr(req, "_get_sale_display_lines"):
            return {"lines": lines, "more": 0, "live": False, "source": ""}

        lines, more = req._get_sale_display_lines(limit=_MAX_PANEL_LINES)
        if not lines:
            return {"lines": [], "more": 0, "live": False, "source": ""}

        names = list(dict.fromkeys(line["order"] for line in lines))
        if len(names) == 1:
            for line in lines:
                line["order"] = ""
        return {
            "lines": lines,
            "more": more,
            "live": True,
            "source": ", ".join(names),
        }

    @staticmethod
    def _reasons_payload(category):
        reasons = category.env["approval.refusal.reason"].search(
            [
                "|",
                ("category_ids", "=", False),
                ("category_ids", "in", category.ids),
                ("active", "=", True),
            ]
        )
        return [{"id": reason.id, "name": reason.name} for reason in reasons]
