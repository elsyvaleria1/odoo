from odoo import models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def _unlink_quality_check(self) -> None:
        # A subcontractor may not read the checks on the lines they are
        # recording, so drop them as superuser.  (`self.sudo(False)` stood
        # here as a third line: `sudo` returns a new recordset, so the call
        # changed nothing and its result was discarded.)
        if self.env.user.partner_id.is_subcontractor and not self.env.su:
            super(StockMoveLine, self.sudo())._unlink_quality_check()
        else:
            super()._unlink_quality_check()
