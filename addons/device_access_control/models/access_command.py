import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AccessCommand(models.Model):
    _name = "access.command"
    _description = "Access Command"
    _order = "create_date desc, id desc"

    device_id = fields.Many2one(
        comodel_name="device.device",
        index=True,
        required=True,
        ondelete="cascade",
    )
    command_type = fields.Selection(
        selection=[
            ("open_door", "Open Door"),
            ("close_door", "Close Door"),
            ("get_status", "Get Status"),
            ("reboot", "Reboot"),
        ],
        required=True,
    )
    payload = fields.Text()
    state = fields.Selection(
        selection=[
            ("pending", "Pending"),
            ("sent", "Sent"),
            ("executed", "Executed"),
            ("error", "Error"),
            ("expired", "Expired"),
        ],
        default="pending",
        index=True,
        required=True,
    )
    result = fields.Text(help="JSON result from command execution.")
    error_message = fields.Text()
    result_image = fields.Binary(attachment=True)
    sent_date = fields.Datetime(readonly=True)
    execute_date = fields.Datetime(readonly=True)

    @api.model
    def _cron_expire_commands(self) -> int:
        threshold = fields.Datetime.subtract(fields.Datetime.now(), minutes=5)
        stale = self.search(
            [
                ("state", "in", ["pending", "sent"]),
                ("create_date", "<", threshold),
            ]
        )
        if stale:
            _logger.info("Expiring %s stale access commands", len(stale))
            stale.write(
                {
                    "state": "expired",
                    "error_message": self.env._(
                        "Command expired: not executed within 5 minutes."
                    ),
                }
            )
        return len(stale)
