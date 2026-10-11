from odoo import models


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    def _get_attachments(self, records, filenames=None):
        if self.env.context.get("snailmail_layout"):
            return {}
        return super()._get_attachments(records, filenames)

    def get_paperformat(self):
        res = super().get_paperformat()
        if self.env.context.get("snailmail_layout") and res != self.env.ref(
            "l10n_de.paperformat_euro_din", False
        ):
            return self.env.ref("base.paperformat_euro")
        else:
            return res
