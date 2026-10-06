from datetime import datetime

from odoo import api, fields, models

from odoo.addons.telegram.tools import keyboard as kb
from odoo.addons.telegram.tools.authority import operating

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y")


class TelegramApprovalNotifier(models.AbstractModel):
    _name = "telegram.approval.notifier"
    _description = "Telegram Approval Notifier"

    @api.model
    def _notify_approver(self, approver, intro=None, resubmitted=False):
        if not approver._telegram_notify_enabled():
            return
        request = approver.request_id
        target = self._target_chat(
            approver._get_effective_approver(), request.company_id
        )
        if not target:
            return
        bot = target.bot_id
        env = self._recipient_env(target)
        if resubmitted:
            intro = env._("🔄 Request corrected and resubmitted")
        bot._queue_text(
            target,
            self._format_summary(request, intro=intro, env=env),
            reply_markup=self._prepare_keyboard(
                approver, request, bot, env=self._recipient_env(target)
            ),
            html=False,
        )

    @api.model
    def _feature_active(self) -> bool:
        return bool(
            operating(self.env["telegram.bot"]).search_count(
                [("notify_approvals", "=", True)], limit=1
            )
        )

    @api.model
    def _recipient_env(self, chat):
        lang = chat.partner_id.lang
        if lang and lang != self.env.lang:
            return self.env(context={**self.env.context, "lang": lang})
        return self.env

    @api.model
    def _target_chat(self, user, company):
        """The chat that tells `user` about a record of `company`: one of a
        bot that speaks for that company, whose buttons and Mini App then
        act in it."""
        if not user:
            return self.env["telegram.chat"].browse()
        bots = operating(self.env["telegram.bot"]).search(
            [("notify_approvals", "=", True), ("company_id", "=", company.id)]
        )
        if not bots:
            return self.env["telegram.chat"].browse()
        return self.env["telegram.chat"]._for_user(user, bots)[:1]

    @api.model
    def _notify_owner_outcome(self, request):
        if not self._feature_active():
            return
        target = self._target_chat(request.request_owner_id, request.company_id)
        if not target:
            return
        env = self._recipient_env(target)
        if request.state == "approved":
            text = env._("✅ Your request %(request)s was APPROVED!") % {
                "request": request.name
            }
        elif request.state == "refused":
            lines = [
                env._("❌ Your request %(request)s was REFUSED.")
                % {"request": request.name}
            ]
            if request.refusal_reason_id:
                lines.append(
                    env._("Reason: %(reason)s")
                    % {"reason": request.refusal_reason_id.name}
                )
            if request.refusal_note:
                lines.append(
                    env._("Comment: %(note)s") % {"note": request.refusal_note}
                )
            text = "\n".join(lines)
        else:
            return
        target.bot_id._queue_text(target, text, html=False)

    @api.model
    def _notify_owner_change(self, request, field, note=None):
        if not self._feature_active():
            return
        target = self._target_chat(request.request_owner_id, request.company_id)
        if not target:
            return
        env = self._recipient_env(target)
        labels = {
            "date": env._("the date"),
            "reason": env._("the description / reason"),
        }
        lines = [
            env._("🔄 A change was requested on your request"),
            env._("Number: %(number)s") % {"number": request.name},
            env._("Correct: %(field)s") % {"field": labels.get(field, field)},
        ]
        if note:
            lines.append(env._("Approver comment: %(note)s") % {"note": note})
        bot = target.bot_id
        url = bot._mini_app_url(f"/telegram/approval/app/{bot.id}/fix/{request.id}")
        fix_button = (
            kb.web_app_button(env._("✏️ Correct"), url)
            if url
            else kb.button(env._("✏️ Correct"), f"ar:fix:{request.id}")
        )
        bot._queue_text(
            target, "\n".join(lines), reply_markup=kb.keyboard([fix_button]), html=False
        )

    @api.model
    def _format_summary(self, request, intro=None, env=None) -> str:
        env = env or self.env
        lines = [
            intro or env._("🔔 New approval request"),
            env._("Number: %(number)s") % {"number": request.name},
            env._("Category: %(category)s") % {"category": request.category_id.name},
            env._("Requester: %(requester)s")
            % {"requester": request.request_owner_id.name},
        ]
        if request.amount:
            currency = request.company_id.currency_id.symbol or ""
            lines.append(
                env._("Amount: %(amount)s")
                % {"amount": f"{currency}{request.amount:,.2f}"}
            )
        if request.partner_id:
            lines.append(
                env._("Contact: %(contact)s") % {"contact": request.partner_id.name}
            )
        if request.reference:
            lines.append(
                env._("Reference: %(reference)s") % {"reference": request.reference}
            )
        if request.date:
            lines.append(
                env._("Date: %(date)s")
                % {"date": fields.Date.to_string(request.date.date())}
            )
        review = self._summary_review_lines(request, env)
        if review:
            lines.append("")
            lines.extend(review)
        lines.append("")
        lines.append(env._("What would you like to do?"))
        return "\n".join(lines)

    @api.model
    def _summary_review_lines(self, request, env):
        """Lines a bridge adds to the approver's summary, after the request's
        own data: a review the approver reads before deciding. None here."""
        return []

    @api.model
    def _prepare_keyboard(self, approver, request, bot, env=None):
        env = env or self.env
        url = bot._mini_app_url(f"/telegram/approval/app/{bot.id}?request={request.id}")
        return kb.keyboard(
            [kb.button(env._("✅ Approve"), f"ar:a:{approver.id}")],
            [
                kb.button(env._("✏️ Request changes"), f"ar:c:{approver.id}"),
                kb.button(env._("❌ Refuse"), f"ar:r:{approver.id}"),
            ],
            [kb.web_app_button(env._("📄 View request"), url)] if url else [],
        )

    @api.model
    def _mini_app_labels(self) -> dict:
        _ = self.env._
        return {
            "lang": (self.env.lang or "en_US").replace("_", "-"),
            "title": _("My approvals"),
            "fix_title": _("Correct request"),
            "loading": _("Loading…"),
            "network": _("Network error."),
            "unlinked": _("Connect this Telegram account to your Odoo user first."),
            "session": _("The session could not be validated."),
            "empty": _("You have no requests. 🎉"),
            "failed": _("It could not be done:"),
            "approve": _("Approve"),
            "changes": _("Changes"),
            "refuse": _("Refuse"),
            "refusal_reason": _("Refusal reason:"),
            "no_reason": _("No specific reason"),
            "comment": _("Comment (optional)"),
            "confirm_refusal": _("Confirm refusal"),
            "field_to_fix": _("Field to correct:"),
            "field_date": _("Date"),
            "field_reason": _("Description / Reason"),
            "change_hint": _("What should the requester correct?"),
            "confirm": _("Confirm"),
            "requester": _("Requester"),
            "amount": _("Amount"),
            "quantity": _("Quantity"),
            "vendor": _("Vendor"),
            "reference": _("Reference"),
            "location": _("Location"),
            "journal": _("Journal"),
            "date": _("Date"),
            "date_start": _("Start"),
            "date_end": _("End"),
            "date_deadline": _("Deadline"),
            "priority": _("Priority"),
            "products": _("Products"),
            "more_lines": _("… and %(count)s more lines"),
            "description": _("Description"),
            "approvers": _("Approvers"),
            "attachments": _("Attachments"),
            "attachment": _("Attachment"),
            "already_approved": _("You already approved"),
            "already_refused": _("You already refused"),
            "not_owner": _("This request no longer needs corrections from you."),
            "request": _("Request:"),
            "to_fix": _("What you must correct:"),
            "new_date": _("New date:"),
            "new_reason": _("New description / reason:"),
            "save_resend": _("Save and resubmit"),
            "fix_sent": _("Correction sent. It is back in approval."),
            "states": {
                "new": _("To submit"),
                "pending": _("Submitted"),
                "approved": _("Approved"),
                "refused": _("Refused"),
            },
            "priorities": {
                "0": _("Low"),
                "1": _("Normal"),
                "2": _("High"),
                "3": _("Urgent"),
            },
        }

    @api.model
    def _approve(self, approver):
        approver.request_id.action_approve(approver=approver)

    @api.model
    def _refuse(self, approver, reason_id=None, note=None):
        request = approver.request_id
        request.write(
            {"refusal_reason_id": reason_id or False, "refusal_note": note or False}
        )
        request.with_context(skip_wizard=True).action_refuse(approver=approver)

    @api.model
    def _request_change(self, approver, field, note=None):
        request = approver.request_id
        request.with_context(
            skip_wizard=True, requested_change_field=field, change_note=note
        ).action_request_change(approver=approver)
        if note:
            request.message_post(
                body=request.env._(
                    "Change requested on \u00ab%(field)s\u00bb: %(note)s"
                )
                % {"field": field, "note": note},
                message_type="notification",
                partner_ids=request.request_owner_id.partner_id.ids,
            )

    @api.model
    def _apply_owner_fix(self, request, raw_value):
        if request.pending_change_field == "date":
            parsed = self._parse_user_date(raw_value)
            if not parsed:
                return False
            request.write({"date": parsed})
        else:
            request.write({"reason": raw_value or ""})
        request.action_resubmit()
        return True

    @staticmethod
    def _parse_user_date(text):
        for date_format in _DATE_FORMATS:
            try:
                parsed = datetime.strptime((text or "").strip(), date_format)
            except ValueError:
                continue
            return fields.Datetime.to_string(parsed.replace(hour=12))
        return None
