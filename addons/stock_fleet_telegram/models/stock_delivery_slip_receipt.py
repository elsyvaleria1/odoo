from odoo import api, fields, models
from odoo.exceptions import UserError

OPEN_STATES = ("draft", "submitted")


class StockDeliverySlipReceipt(models.Model):

    _name = "stock.delivery.slip.receipt"
    _description = "Signed Delivery Slip Receipt"
    _inherit = ["mixin.mail.thread"]
    _order = "id desc"

    name = fields.Char(
        string="Folio",
        default="/",
        copy=False,
        readonly=True,
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("submitted", "To Receive"),
            ("done", "Received"),
            ("cancel", "Cancelled"),
        ],
        default="draft",
        copy=False,
        readonly=True,
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
    )
    delivered_by_id = fields.Many2one(
        comodel_name="res.users",
        tracking=True,
        help="Who delivered the goods and hands the signed slips over: the user "
        "who sent their photos through Telegram.",
    )
    received_by_id = fields.Many2one(
        comodel_name="res.users",
        tracking=True,
        help="Who received the signed slips on paper. Set on confirmation when "
        "left empty.",
    )
    date_receipt = fields.Datetime(
        string="Received On",
        copy=False,
        readonly=True,
    )
    telegram_chat_id = fields.Many2one(
        comodel_name="telegram.chat",
        index="btree_not_null",
        readonly=True,
        ondelete="set null",
        help="The chat whose slips this batch gathers while it is open.",
    )
    slip_ids = fields.One2many(
        comodel_name="telegram.delivery.slip",
        inverse_name="receipt_id",
        string="Delivery Slips",
        copy=False,
    )
    slip_count = fields.Integer(
        string="Slips",
        compute="_compute_slip_count",
    )
    note = fields.Text()

    @api.depends("slip_ids")
    def _compute_slip_count(self) -> None:
        for receipt in self:
            receipt.slip_count = len(receipt.slip_ids)

    @api.model
    def _get_or_create_open_receipt_for_chat(self, chat, company, user):
        receipt = self.search(
            [
                ("telegram_chat_id", "=", chat.id),
                ("company_id", "=", company.id),
                ("state", "=", "draft"),
            ],
            limit=1,
        )
        return receipt or self.create(
            {
                "telegram_chat_id": chat.id,
                "company_id": company.id,
                "delivered_by_id": user.id,
            }
        )

    def _submit_from_telegram(self) -> None:
        self.filtered(lambda receipt: receipt.state == "draft").write(
            {"state": "submitted"}
        )

    def action_confirm(self) -> dict:
        self.check_singleton()
        if self.state not in OPEN_STATES:
            raise UserError(self.env._("Only an open batch can be confirmed."))
        if not self.slip_ids:
            raise UserError(
                self.env._("The batch has no delivery slip left to receive.")
            )
        pickings = self.slip_ids.picking_id
        received = pickings.filtered("delivery_paper_received")
        if received:
            raise UserError(
                self.env._(
                    "The paper of %(pickings)s was already received. Remove it "
                    "from this batch before confirming.",
                    pickings=", ".join(received.mapped("name")),
                )
            )
        pickings.action_receive_delivery_paper()
        self.write(
            {
                "state": "done",
                "received_by_id": self.received_by_id.id or self.env.uid,
                "date_receipt": fields.Datetime.now(),
                "name": self.env["ir.sequence"]
                .with_company(self.company_id)
                .next_by_code("stock.delivery.slip.receipt"),
            }
        )
        for picking in pickings:
            picking.message_post(
                body=self.env._("Signed slip received on paper in batch %s.", self.name)
            )
        pdf, _report_type = self.env["ir.actions.report"]._render_qweb_pdf(
            "stock_fleet_telegram.action_report_delivery_slip_receipt", self.ids
        )
        self.message_post(
            body=self.env._(
                "Delivery slip reception %(name)s confirmed: %(count)s slips, "
                "delivered by %(deliverer)s, received by %(receiver)s.",
                name=self.name,
                count=len(self.slip_ids),
                deliverer=self.delivered_by_id.name or "-",
                receiver=self.received_by_id.name or "-",
            ),
            attachments=[
                (self.env._("Delivery Slip Reception %s.pdf", self.name), pdf)
            ],
        )
        return self.action_print()

    def action_print(self) -> dict:
        return self.env.ref(
            "stock_fleet_telegram.action_report_delivery_slip_receipt"
        ).report_action(self)

    def action_cancel(self) -> None:
        for receipt in self:
            if receipt.state == "done":
                pickings = receipt.slip_ids.picking_id.filtered(
                    "delivery_paper_received"
                )
                pickings.write({"delivery_paper_received": False})
                for picking in pickings:
                    picking.message_post(
                        body=self.env._(
                            "Paper reception reverted: batch %s cancelled.",
                            receipt.name,
                        )
                    )
        self.state = "cancel"

    def action_draft(self) -> None:
        self.filtered(
            lambda receipt: receipt.state == "cancel" and receipt.name == "/"
        ).state = "draft"
