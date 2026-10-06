from odoo import api, fields, models


class TelegramFinancialReportLog(models.Model):
    _name = "telegram.financial.report.log"
    _description = "Telegram Financial Report Log"
    _order = "date desc, id desc"

    date = fields.Datetime(
        default=fields.Datetime.now,
        readonly=True,
        required=True,
    )
    chat_id = fields.Many2one(
        comodel_name="telegram.chat",
        string="Chat Session",
        readonly=True,
        ondelete="set null",
    )
    telegram_chat_id = fields.Char(
        string="Telegram Chat ID",
        readonly=True,
        help="The Telegram chat ID where the report was sent",
    )
    requester_partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Requester",
        readonly=True,
        help="Odoo Contact who requested and received the PDF",
    )
    target_partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Report Subject",
        readonly=True,
        required=True,
        help="The partner whose account statement was generated",
    )
    date_from = fields.Date(
        string="Period From",
        readonly=True,
    )
    date_to = fields.Date(
        string="Period To",
        readonly=True,
    )
    success = fields.Boolean(
        string="Delivered",
        default=True,
        readonly=True,
        help="Whether the PDF was successfully sent to the user",
    )
    is_self_request = fields.Boolean(
        string="Self Request",
        compute="_compute_is_self_request",
        store=True,
        help="True if the requester requested their own statement",
    )
    requester_role = fields.Selection(
        selection=[
            ("user", "User"),
            ("manager", "Manager"),
        ],
        readonly=True,
        help="Role of the requester at the time of the request",
    )

    @api.depends("requester_partner_id", "target_partner_id")
    def _compute_is_self_request(self) -> None:
        for record in self:
            record.is_self_request = (
                record.requester_partner_id == record.target_partner_id
            )
