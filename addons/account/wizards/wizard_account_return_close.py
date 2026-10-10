from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardAccountReturnClose(models.TransientModel):
    _name = "wizard.account.return.close"
    _description = "Close a Return Handled Outside Odoo"

    return_id = fields.Many2one(
        comodel_name="account.return",
        readonly=True,
        required=True,
    )
    reason = fields.Text(required=True)

    @_debug.perf.timed
    def action_close(self) -> dict | None:
        _debug.lifecycle("action_close", records=self, tax_return=self.return_id)
        self.check_singleton()
        return self.return_id._close_outside_odoo(self.reason)
