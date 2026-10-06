from odoo import api, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class IrSequence(models.Model):
    _inherit = "ir.sequence"

    @api.ondelete(at_uninstall=False)
    def _unlink_sequence(self) -> None:
        configs = self.env["pos.config"].search(
            domain=[
                "|",
                "|",
                "|",
                ("order_seq_id", "in", self.ids),
                ("order_line_seq_id", "in", self.ids),
                ("device_seq_id", "in", self.ids),
                ("order_backend_seq_id", "in", self.ids),
            ]
        )
        if len(configs):
            _debug.logic("sequence_unlink_refused", sequences=self, configs=configs)
            raise UserError(
                self.env._(
                    "You cannot delete a sequence used in an active POS config: %s",
                    configs.order_seq_id.mapped("name"),
                )
            )
