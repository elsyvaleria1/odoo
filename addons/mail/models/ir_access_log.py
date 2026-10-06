from odoo import fields, models

from odoo.addons.base.models.ir_access_log import kept_on_uninstall

MAIL_LOG_EVENTS = [("activity_successor_skipped", "Activity successor skipped")]


class IrAccessLog(models.Model):
    _inherit = "ir.access.log"

    event = fields.Selection(
        selection_add=MAIL_LOG_EVENTS,
        ondelete=kept_on_uninstall(MAIL_LOG_EVENTS),
    )
