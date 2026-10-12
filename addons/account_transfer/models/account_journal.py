from odoo import api, models

from odoo.addons.base.models.ir_model_common import MODULE_UNINSTALL_FLAG


class AccountJournal(models.Model):
    _inherit = "account.journal"

    @api.ondelete(at_uninstall=True)
    def _unlink_cascade_transfer_model(self) -> None:
        if self.env.context.get(MODULE_UNINSTALL_FLAG):
            self.env["account.transfer.model"].search(
                [("journal_id", "in", self.ids)]
            ).unlink()
