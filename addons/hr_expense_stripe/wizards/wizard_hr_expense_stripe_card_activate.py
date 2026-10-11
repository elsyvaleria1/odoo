from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import frozendict

from odoo.addons.hr_expense_stripe.utils import send_request_stripe_proxy


class WizardHrExpenseStripeCardActivate(models.TransientModel):
    _name = "wizard.hr.expense.stripe.card.activate"
    _description = "A wizard used to first active a card when received"
    _access_anchors = frozendict(
        {
            "owner": "card_id.user_id",
        }
    )

    card_id = fields.Many2one(
        comodel_name="hr.expense.stripe.card",
        string="Card to activate",
        required=True,
    )
    card_last_4 = fields.Char(related="card_id.last_4")

    last_4_challenge = fields.Char(
        string="Card Last 4 digits",
        size=4,
        help="The last 4 digits of the card you received. This is used to confirm that you have received the correct card.",
    )
    phone_number = fields.Char(
        string="Cardholder Mobile Number",
        required=True,
        help="Viewing confidential card details requires 2FA authentication. Make sure the cardholder mobile number is correct.",
    )

    is_confirmed = fields.Boolean(
        default=False,
        required=True,
    )
    original_phone_number = fields.Char(required=True)
    billing_country_code = fields.Char(required=True)

    show_warning_wrong_last_4 = fields.Boolean(
        compute="_compute_show_warning_wrong_last_4"
    )

    @api.depends("last_4_challenge", "card_last_4")
    def _compute_show_warning_wrong_last_4(self) -> None:
        for wizard in self:
            wizard.show_warning_wrong_last_4 = (
                wizard.last_4_challenge
                and wizard.last_4_challenge != wizard.card_last_4
            )

    def _create_tracking_message(self) -> None:
        self.check_singleton()
        subtype = self.env.ref(
            "hr_expense_stripe.mt_stripe_cardholder_updated", raise_if_not_found=False
        )
        tracking_values = self.env["mail.tracking.value"]._prepare_tracking_values(
            initial_value=self.original_phone_number,
            new_value=self.original_phone_number,
            col_name="phone_number",
            col_info=self.fields_get(
                ["phone_number"],
                attributes=("string", "type", "selection", "currency_field"),
            )["phone_number"],
            record=self,
        )
        common_vals = {
            "model": "hr.expense.stripe.card",
            "author_id": self.env.user.partner_id.id,
            "tracking_value_ids": [Command.create(tracking_values)],
            "message_type": "notification",
        }
        create_vals = []
        if subtype:
            common_vals["subtype_id"] = subtype.id
        cardholder_user_su = self.sudo().card_id.employee_id.user_id
        cards_su = cardholder_user_su.stripe_card_ids.filtered(
            lambda card: card.company_id == self.card_id.company_id
        )
        for card_su in cards_su:
            create_vals += [{**common_vals, "res_id": card_su.id}]
        if create_vals:
            self.env["mail.message"].create(create_vals)

    def open_expense_stripe_card_receive_terms(self) -> dict:
        return {
            "type": "ir.actions.client",
            "tag": "hr_expense_stripe.expense_stripe_card_receive_terms",
        }

    def action_receive_card(self) -> None:
        for wizard in self:
            if not wizard.is_confirmed:
                raise UserError(
                    self.env._(
                        "You must confirm that you have received the card before activating it."
                    )
                )

            if wizard.last_4_challenge != wizard.card_last_4:
                raise UserError(
                    self.env._(
                        "The last 4 digits you entered do not match the card you received. Please check and try again."
                    )
                )

            if wizard.phone_number != wizard.original_phone_number:
                billing_country = self.env["res.country"].search(
                    domain=[("code", "ilike", self.billing_country_code)],
                    limit=1,
                )
                phone_number = wizard.card_id.employee_id._phone_format(
                    number=wizard.phone_number,
                    country=billing_country,
                    force_format="E164",
                )

                send_request_stripe_proxy(
                    self.card_id.company_id.sudo(),
                    "cardholders/{cardholder_id}",
                    route_params={
                        "cardholder_id": self.card_id.employee_id.sudo().private_stripe_id
                    },
                    payload={
                        "account": self.card_id.company_id.sudo().stripe_id,
                        "phone_number": phone_number,
                    },
                    method="POST",
                )
                self._create_tracking_message()

            card_sudo = wizard.card_id.sudo(
                wizard.card_id.employee_id.user_id == self.env.user or self.env.su
            )
            card_sudo.is_delivered = True
            card_sudo._create_or_update_card(state="active")
