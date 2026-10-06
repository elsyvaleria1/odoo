from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class MixinTenderAgreement(models.AbstractModel):
    _name = "mixin.tender.agreement"
    _description = "Tender Awarded into Agreements"

    award_as = fields.Selection(
        selection=[
            ("orders", "Orders"),
            ("agreements", "Agreements"),
        ],
        string="Award As",
        default="orders",
        required=True,
        tracking=True,
        help="Orders: the award confirms each winning offer. Agreements: the award "
        "opens a blanket agreement with each winner for the period, and orders "
        "are released from it later.",
    )
    date_start = fields.Date(
        string="Supply From",
        help="The first day of the agreements the award opens.",
    )
    date_end = fields.Date(
        string="Supply Until",
        help="The last day of the agreements the award opens.",
    )
    agreement_commitment = fields.Selection(
        selection=[
            ("price", "Prices Only"),
            ("quantity", "Quantity"),
            ("value", "Value"),
        ],
        string="Commitment",
        default="quantity",
        required=True,
        help="What the agreements the award opens commit: the prices only, each "
        "awarded quantity, or the awarded total.",
    )
    agreement_ids = fields.Many2many(
        comodel_name="mixin.agreement",
        string="Agreements",
        compute="_compute_agreement_ids",
    )
    agreement_count = fields.Integer(
        string="Agreement Count",
        compute="_compute_agreement_ids",
    )

    @api.depends("order_ids.awarded_agreement_id")
    def _compute_agreement_ids(self) -> None:
        for tender in self:
            tender.agreement_ids = tender.order_ids.awarded_agreement_id
            tender.agreement_count = len(tender.agreement_ids)

    def _award_to(self, winners, awarded_lines):
        if self.award_as != "agreements":
            return super()._award_to(winners, awarded_lines)
        Agreement = self.env[winners._fields["awarded_agreement_id"].comodel_name]
        for order in winners:
            agreement = Agreement.create(
                order._prepare_awarded_agreement_values(
                    self, order.line_ids & awarded_lines
                )
            )
            agreement.action_confirm()
            order._close_into(agreement)
        _debug.lifecycle(
            "tender_awarded_into_agreements",
            tender=self,
            agreements=winners.awarded_agreement_id,
        )
        return None

    def action_view_agreements(self):
        self.check_singleton()
        agreements = self.agreement_ids
        action = {
            "name": self.env._("Agreements"),
            "type": "ir.actions.act_window",
            "res_model": agreements._name,
            "domain": [("id", "in", agreements.ids)],
            "view_mode": "list,form",
        }
        if len(agreements) == 1:
            action.update({"view_mode": "form", "res_id": agreements.id})
        return action


class MixinOrderTenderAgreement(models.AbstractModel):
    _name = "mixin.order.tender.agreement"
    _description = "Offer Awarded into an Agreement"

    awarded_agreement_id = fields.Many2one(
        comodel_name="mixin.agreement",
        string="Awarded Into",
        index="btree_not_null",
        copy=False,
        readonly=True,
        help="The agreement this offer's award opened. The offer itself closes "
        "as won; orders are released from the agreement.",
    )

    @api.depends("state", "awarded_agreement_id")
    def _compute_outcome(self) -> None:
        super()._compute_outcome()
        for order in self:
            if order.state == "cancel" and order.awarded_agreement_id:
                order.outcome = "won"

    def _prepare_awarded_agreement_values(self, tender, lines) -> dict:
        self.check_singleton()
        line_values = [
            self._prepare_awarded_agreement_line_values(line) for line in lines
        ]
        return {
            "partner_id": self.partner_id.id,
            "company_id": self.company_id.id,
            "currency_id": self.currency_id.id,
            "user_id": (tender.user_id or self.user_id).id,
            "reference": tender.name,
            "date_start": tender.date_start,
            "date_end": tender.date_end,
            "commitment": tender.agreement_commitment,
            "amount_committed": (
                sum(vals["product_qty"] * vals["price_unit"] for vals in line_values)
                if tender.agreement_commitment == "value"
                else 0.0
            ),
            "line_ids": [fields.Command.create(vals) for vals in line_values],
        }

    def _prepare_awarded_agreement_line_values(self, line) -> dict:
        return {
            "product_id": line.product_id.id,
            "product_uom_id": line.product_uom_id.id,
            "product_qty": line.qty_awarded,
            "price_unit": line.price_unit * (1 - (line.discount or 0.0) / 100),
        }

    def _close_into(self, agreement) -> None:
        self.check_singleton()
        self._check_cancel_allowed()
        self.awarded_agreement_id = agreement
        self._action_cancel()
