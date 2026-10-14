from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class MailActivity(models.Model):
    _inherit = "mail.activity"

    account_return_check_template_id = fields.Many2one(
        comodel_name="account.return.check.template",
        string="Return Check Template",
        readonly=True,
        ondelete="set null",
    )

    @_debug.perf.timed
    def action_view_document(self):
        _debug.lifecycle("action_view_document", records=self)
        if self.res_model != "account.return":
            return super().action_view_document()

        return (
            self.env["account.return"].browse(self.res_id).action_view_account_return()
        )
