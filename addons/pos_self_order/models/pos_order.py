import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    combo_id = fields.Many2one(
        comodel_name="product.combo",
        string="Combo reference",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("combo_parent_uuid"):
                vals.update(
                    [
                        (
                            "combo_parent_id",
                            self.search(  # noqa: E8507 - one lookup per created combo line, on its parent uuid
                                [("uuid", "=", vals.get("combo_parent_uuid"))]
                            ).id,
                        )
                    ]
                )
            if "combo_parent_uuid" in vals:
                del vals["combo_parent_uuid"]
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("combo_parent_uuid"):
            vals.update(
                [
                    (
                        "combo_parent_id",
                        self.search([("uuid", "=", vals.get("combo_parent_uuid"))]).id,
                    )
                ]
            )
        if "combo_parent_uuid" in vals:
            del vals["combo_parent_uuid"]
        return super().write(vals)


class PosOrder(models.Model):
    _inherit = "pos.order"

    table_stand_number = fields.Char()
    kiosk_payment_to_verify = fields.Char(
        string="Kiosk Payment to Verify",
        copy=False,
        readonly=True,
        help="Reference of a kiosk terminal payment whose outcome is unknown: "
        "the kiosk takes no other payment for the order until staff check the "
        "terminal and record it as approved or not.",
    )
    kiosk_payment_to_verify_method_id = fields.Many2one(
        comodel_name="pos.payment.method",
        copy=False,
        readonly=True,
    )
    kiosk_payment_to_verify_amount = fields.Monetary(
        currency_field="currency_id",
        copy=False,
        readonly=True,
    )
    self_ordering_table_id = fields.Many2one(
        comodel_name="restaurant.table",
        string="Table reference",
        readonly=True,
    )
    source = fields.Selection(
        selection_add=[("mobile", "Self-Order Mobile"), ("kiosk", "Self-Order Kiosk")]
    )
    kiosk_terminal_reference = fields.Char(
        copy=False,
        readonly=True,
        help="The reference the kiosk's latest terminal payment request was sent with.",
    )
    kiosk_terminal_request = fields.Char(
        copy=False,
        readonly=True,
        help="The terminal provider's id of that request.",
    )

    def _set_kiosk_terminal_request(self, reference, request_id) -> None:
        self.check_singleton()
        self.write(
            {
                "kiosk_terminal_reference": reference,
                "kiosk_terminal_request": request_id and str(request_id),
            }
        )

    def _add_kiosk_terminal_payment(self, payment_method, values) -> bool:
        """Pay the whole order with a transaction its kiosk's terminal approved.

        The caller has checked the transaction is the one requested for this
        order, for its amount. False when it already paid this order; raises
        UserError when it paid another one or the order awaits no payment.
        """
        self.check_singleton()
        transaction_id = values.get("transaction_id")
        if not transaction_id:
            raise UserError(self.env._("The terminal approved no transaction."))
        self.lock_for_update(wait=True)
        recorded = (
            self.env["pos.payment"]
            .sudo()
            .search(
                [
                    ("transaction_id", "=", str(transaction_id)),
                    (
                        "payment_method_id.use_payment_terminal",
                        "=",
                        payment_method.use_payment_terminal,
                    ),
                ]
            )
        )
        if recorded.pos_order_id - self:
            raise UserError(self.env._("This transaction already paid another order."))
        if recorded:
            return False
        if self.state != "draft":
            raise UserError(self.env._("This order is not awaiting a payment."))
        self.add_payment(
            {
                **values,
                "transaction_id": str(transaction_id),
                "amount": self.amount_total,
                "payment_method_id": payment_method.id,
                "pos_order_id": self.id,
            }
        )
        self.action_pos_order_paid()
        return True

    def write(self, vals):
        if "table_id" in vals and self.self_ordering_table_id:
            # Clear stale self-order table link when the order is transferred to a new table.
            vals["self_ordering_table_id"] = vals["table_id"]
        return super().write(vals)

    @api.model
    def _load_pos_self_data_domain(self, data, config):
        return [("id", "=", False)]

    @api.model
    def remove_from_ui(self, server_ids):
        orders = self.env["pos.order"].browse(server_ids)
        # An order the customer placed from their own device is never deleted
        # out from under them: it is cancelled and kept, so their history still
        # lists it and the ORDER_STATE_CHANGED they receive names a state their
        # device can show. super() selects on state = draft, so the cancelled
        # ones are exactly the ones it leaves alone.
        self_orders = orders.filtered(lambda o: o.source in ("kiosk", "mobile"))
        self_orders._cancel_draft_orders()
        # before super(), which unlinks the rest: config_id is unreadable after.
        self._notify_order_state_changed(orders)
        return super().remove_from_ui(server_ids)

    @api.model
    def sync_from_ui(self, orders):
        result = super().sync_from_ui(orders)
        order_ids = self.browse(
            [order["id"] for order in result["pos.order"] if order.get("id")]
        )
        self._notify_order_state_changed(order_ids)
        return result

    def action_pos_order_cancel(self):
        orders = super().action_pos_order_cancel()
        success_orders_ids = [
            o["id"] for o in orders["pos.order"] if o["state"] == "cancel"
        ]
        orders_ids = self.browse(success_orders_ids)
        self._notify_order_state_changed(orders_ids)
        return orders

    def _notify_order_state_changed(self, order_ids) -> None:
        # point_of_sale already emits SYNCHRONISATION for each of these three
        # transitions, so this override adds only the message it owns
        for config in order_ids.config_id:
            config._notify("ORDER_STATE_CHANGED", {})

    def _send_self_order_receipt(self) -> None:
        if self.email:
            try:
                self.action_send_self_order_receipt(
                    self.email, self.preset_id.mail_template_id.id, False, False
                )
            except UserError as e:
                _logger.warning("Error while sending email: %s", e.args[0])

    def action_send_self_order_receipt(
        self, email, mail_template_id, ticket_image, basic_image
    ) -> None:
        self.check_singleton()
        self.email = email
        mail_template = self.env["mail.template"].browse(mail_template_id)
        if not mail_template:
            raise UserError(
                self.env._(
                    "The mail template with xmlid %s has been deleted.",
                    mail_template_id,
                )
            )
        email_values = {"email_to": email}
        if self.state == "paid" and ticket_image:
            email_values["attachment_ids"] = self._create_mail_attachments(
                self.name, ticket_image, basic_image
            )
        mail_template.send_mail(self.id, force_send=True, email_values=email_values)

    def _hold_kiosk_payment_to_verify(self, payment_method, amount, reference):
        self.check_singleton()
        self.write(
            {
                "kiosk_payment_to_verify": reference,
                "kiosk_payment_to_verify_method_id": payment_method.id,
                "kiosk_payment_to_verify_amount": amount,
            }
        )
        self._send_payment_result("unverified")

    def _clear_kiosk_payment_to_verify(self):
        self.write(
            {
                "kiosk_payment_to_verify": False,
                "kiosk_payment_to_verify_method_id": False,
                "kiosk_payment_to_verify_amount": 0.0,
            }
        )

    def action_kiosk_payment_approved(self):
        for order in self.filtered("kiosk_payment_to_verify_method_id"):
            payment = {
                "amount": order.kiosk_payment_to_verify_amount,
                "payment_date": fields.Datetime.now(),
                "payment_method_id": order.kiosk_payment_to_verify_method_id.id,
                "transaction_id": order.kiosk_payment_to_verify,
                "payment_status": "Success",
                "pos_order_id": order.id,
            }
            order._clear_kiosk_payment_to_verify()
            order.add_payment(payment)
            order.action_pos_order_paid()
            order._send_payment_result("Success")

    def action_kiosk_payment_not_approved(self):
        for order in self.filtered("kiosk_payment_to_verify_method_id"):
            order._clear_kiosk_payment_to_verify()
            order._send_payment_result("fail")

    def _send_payment_result(self, payment_result) -> None:
        self.check_singleton()
        self.config_id._notify(
            "PAYMENT_STATUS",
            {
                "payment_result": payment_result,
                "data": {
                    "pos.order": self.read(
                        self._load_pos_self_data_fields(self.config_id), load=False
                    ),
                    "pos.order.line": self.lines.read(
                        self.lines._load_pos_self_data_fields(self.config_id),
                        load=False,
                    ),
                },
            },
        )
        if payment_result == "Success":
            self._send_order()

    @api.model
    def _load_pos_data_fields(self, config):
        return super()._load_pos_data_fields(config) + [
            "self_ordering_table_id",
            "table_stand_number",
        ]

    def _load_pos_self_data_fields(self, config):
        return [
            "id",
            "uuid",
            "name",
            "display_name",
            "access_token",
            "receipt_token",
            "last_order_preparation_change",
            "date_order",
            "amount_total",
            "amount_paid",
            "amount_return",
            "user_id",
            "amount_tax",
            "lines",
            "pricelist_id",
            "company_id",
            "country_code",
            "sequence_number",
            "session_id",
            "config_id",
            "currency_id",
            "currency_rate",
            "is_refund",
            "has_refundable_lines",
            "state",
            "account_move",
            "preset_id",
            "floating_order_name",
            "general_customer_note",
            "internal_note",
            "nb_print",
            "pos_reference",
            "kiosk_payment_to_verify",
            "kiosk_payment_to_verify_method_id",
            "fiscal_position_id",
            "payment_ids",
            "to_invoice",
            "shipping_date",
            "preset_time",
            "is_invoiced",
            "is_tipped",
            "tip_amount",
            "ticket_code",
            "tracking_number",
            "email",
            "phone_ids",
            "table_id",
            "course_ids",
            "table_stand_number",
            "self_ordering_table_id",
            "create_date",
            "write_date",
            "source",
            "partner_id",
            "customer_count",
        ]
