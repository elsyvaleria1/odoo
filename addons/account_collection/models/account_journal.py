from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AccountJournal(models.Model):
    _inherit = "account.journal"

    is_collection_custody = fields.Boolean(
        string="Collection Custody",
        help="A customer payment recorded here stays in its collector's custody, "
        "booked to the inbound payment method's outstanding account, until a "
        "remittance hands it in.",
    )

    @api.constrains("is_collection_custody", "type", "inbound_payment_channel_ids")
    def _check_collection_custody(self) -> None:
        for journal in self.filtered("is_collection_custody"):
            if problem := journal._get_collection_custody_problem():
                raise ValidationError(problem)

    def _get_collection_custody_problem(self) -> str | None:
        self.check_singleton()
        if self.type not in ("bank", "cash"):
            return self.env._(
                "Journal %(journal)s holds collections in custody, so it must be a "
                "bank or cash journal.",
                journal=self.display_name,
            )
        channels = self.inbound_payment_channel_ids
        if not channels:
            return self.env._(
                "Journal %(journal)s holds collections in custody but receives no "
                "payment method.",
                journal=self.display_name,
            )
        for channel in channels:
            account = channel.payment_account_id
            if (
                not account
                or not account.reconcile
                or account.account_type == "asset_cash"
            ):
                return self.env._(
                    "Journal %(journal)s holds collections in custody: its payment "
                    "method %(method)s must book to a reconcilable outstanding "
                    "account that is not a cash account, or a collection would count "
                    "as money already handed in.",
                    journal=self.display_name,
                    method=channel.display_name,
                )
        return None
