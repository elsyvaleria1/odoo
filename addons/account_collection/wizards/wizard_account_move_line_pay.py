from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.account_collection.models.account_payment import COLLECTION_METHODS


class WizardAccountMoveLinePay(models.TransientModel):
    _inherit = "wizard.account.move.line.pay"

    is_collection_custody = fields.Boolean(
        related="journal_id.is_collection_custody",
    )
    collector_id = fields.Many2one(
        comodel_name="res.users",
        compute="_compute_collector_id",
        store=True,
        readonly=False,
        help="Who received the money from the customer.",
    )
    collection_method = fields.Selection(
        selection=COLLECTION_METHODS,
        string="Collected In",
        compute="_compute_collection_method",
        store=True,
        readonly=False,
    )

    collection_check_date = fields.Date(
        string="Check Date",
        help="The date written on the check, when it is post-dated.",
    )

    @api.depends("journal_id")
    def _compute_collector_id(self) -> None:
        for wizard in self:
            if wizard.is_collection_custody and not wizard.collector_id:
                wizard.collector_id = self.env.user

    @api.depends("journal_id")
    def _compute_collection_method(self) -> None:
        for wizard in self:
            if wizard.is_collection_custody and not wizard.collection_method:
                wizard.collection_method = "cash"

    def _get_collection_payment_vals(self) -> dict:
        return {
            "collector_id": self.collector_id.id,
            "collection_method": self.collection_method,
            "collection_check_date": self.collection_method == "check"
            and self.collection_check_date,
        }

    def _create_payment_vals_from_wizard(self, batch_result):
        return {
            **super()._create_payment_vals_from_wizard(batch_result),
            **self._get_collection_payment_vals(),
        }

    def _create_payment_vals_from_batch(self, batch_result):
        return {
            **super()._create_payment_vals_from_batch(batch_result),
            **self._get_collection_payment_vals(),
        }

    def _create_payments(self):
        self.check_singleton()
        if not self.is_collection_custody:
            return super()._create_payments()
        if not self.collector_id or not self.collection_method:
            raise UserError(
                self.env._(
                    "A collection held in custody names its collector and how the "
                    "customer paid."
                )
            )
        if self.payment_type != "inbound" or self.partner_type != "customer":
            raise UserError(
                self.env._(
                    "Journal %(journal)s holds customer collections only.",
                    journal=self.journal_id.display_name,
                )
            )
        return super()._create_payments()
