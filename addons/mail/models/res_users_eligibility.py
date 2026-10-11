from markupsafe import Markup

from odoo import models


class ResUsersEligibility(models.Model):
    _inherit = "res.users.eligibility"

    def _log(self, event: str, grant: models.BaseModel, reason: str | None) -> None:
        super()._log(event, grant, reason)
        if event in ("elevation_activated", "break_glass_opened"):
            self._notify_administrators(event, grant, reason)

    def _notify_administrators(
        self, event: str, grant: models.BaseModel, reason: str | None
    ) -> None:
        read = self.env["ir.access"]._access_evaluator
        administrators = read("res.groups").browse(
            [
                group.id
                for xmlid in ("base.group_system", "base.group_erp_manager")
                if (group := self.env.ref(xmlid, raise_if_not_found=False))
            ]
        )
        eligible = read("res.users.eligibility").search(
            [("group_id", "in", administrators.ids), ("state", "=", "active")]
        )
        recipients = (administrators.all_user_ids | eligible.user_id).filtered(
            lambda user: user.active and not user.share
        ) - self.user_id
        if not recipients:
            return
        for eligibility in self:
            subject = (
                self.env._(
                    "Break-glass opened by %(user)s", user=eligibility.user_id.name
                )
                if event == "break_glass_opened"
                else self.env._(
                    "%(user)s activated %(group)s",
                    user=eligibility.user_id.name,
                    group=eligibility.group_id.full_name,
                )
            )
            body = Markup("<p>%s</p><p>%s</p>") % (
                self.env._(
                    "%(group)s until %(until)s.",
                    group=eligibility.group_id.full_name,
                    until=grant.date_to,
                ),
                self.env._("Why: %s", reason or "-"),
            )
            self.env["mixin.mail.thread"].message_notify(
                partner_ids=recipients.partner_id.ids, subject=subject, body=body
            )
