from typing import Any

from markupsafe import Markup, escape

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools import format_amount

from odoo.addons.approval.models.mixin_approval import APPROVAL_TRIGGER_CATEGORY


class AccountCollectionRemittance(models.Model):
    _name = "account.collection.remittance"
    _inherit = ["account.collection.remittance", "mixin.approval.gate"]

    receiver_id = fields.Many2one(
        comodel_name="res.users",
        string="Received By",
        copy=False,
        readonly=True,
        tracking=True,
        help="The treasury user who asked to validate a cash hand-in: the party "
        "who receives the cash from the collector and approves it with them.",
    )

    def _get_approval_trigger(self) -> str | None:
        self.check_singleton()
        if self.destination_type != "cash":
            return None
        return APPROVAL_TRIGGER_CATEGORY

    def _get_domain_approval_category(self) -> list[tuple[str, str, Any]]:
        return [("approval_type", "=", "collection_hand_in")]

    def _get_fields_approval_protected(self) -> list[str]:
        return [
            "payment_ids",
            "amount_handed_in",
            "destination_journal_id",
            "collector_id",
            "receiver_id",
        ]

    def _get_approval_snapshot(self, operation: str) -> dict[str, Any]:
        self.check_singleton()
        return {
            "payments": sorted(self.payment_ids.ids),
            "amount_handed_in": repr(self.amount_handed_in),
            "destination": self.destination_journal_id.id,
            "collector": self.collector_id.id,
            "receiver": self.receiver_id.id,
        }

    def _check_before_approval(self, verb: str) -> None:
        super()._check_before_approval(verb)
        if verb != "validate":
            return
        for remittance in self:
            if (
                remittance.destination_type == "cash"
                and remittance.collector_id == self.env.user
            ):
                raise UserError(
                    self.env._(
                        "%(remittance)s is your own cash: someone else receives it.",
                        remittance=remittance.display_name,
                    )
                )

    def _run_through_approval(self, operation: str, run: Any) -> Any:
        if operation == "validate":
            self.filtered(
                lambda r: r._get_approval_trigger() and not r.approval_request_id
            ).receiver_id = self.env.user
        return super()._run_through_approval(operation, run)

    def _prepare_approval_request_values(self, category: Any) -> dict[str, Any]:
        values = super()._prepare_approval_request_values(category)
        values.update(
            {
                "amount": self.amount_handed_in,
                "date": self.date,
            }
        )
        return values

    def _get_approval_reason_html(self) -> str:
        self.check_singleton()
        rows = [
            (self.env._("Collector"), self.collector_id.name),
            (self.env._("Received by"), self.receiver_id.name),
            (self.env._("Till"), self.destination_journal_id.name),
            (
                self.env._("Amount handed in"),
                format_amount(self.env, self.amount_handed_in, self.currency_id),
            ),
            (self.env._("Collections"), str(len(self.payment_ids))),
        ]
        return Markup("<ul>%s</ul>") % Markup("").join(
            Markup("<li><strong>%s:</strong> %s</li>") % (escape(label), escape(value))
            for label, value in rows
        )
