from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import ValidationError
from odoo.fields import Domain


class WizardLoyaltyProgramCreateCard(models.TransientModel):
    _name = "wizard.loyalty.program.create.card"
    _description = "Generate Coupons"

    program_id = fields.Many2one(
        comodel_name="loyalty.program",
        default=lambda self: (
            self.env.context.get("active_id", False)
            or self.env.context.get("default_program_id", False)
        ),
        required=True,
    )
    program_type = fields.Selection(related="program_id.program_type")

    mode = fields.Selection(
        selection=[
            ("anonymous", "Anonymous Customers"),
            ("selected", "Selected Customers"),
        ],
        string="For",
        default="anonymous",
        required=True,
    )

    customer_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Customers",
    )
    customer_tag_ids = fields.Many2many(
        comodel_name="res.partner.tag",
        string="Customer Tags",
    )

    coupon_qty = fields.Integer(
        string="Quantity",
        compute="_compute_coupon_qty",
        store=True,
        readonly=False,
    )
    points_granted = fields.Float(
        string="Grant",
        default=1,
        required=True,
    )
    points_name = fields.Char(
        related="program_id.portal_point_name",
        readonly=True,
    )
    valid_until = fields.Date()
    will_send_mail = fields.Boolean(compute="_compute_will_send_mail")
    confirmation_message = fields.Char(compute="_compute_confirmation_message")
    description = fields.Text()

    def _get_partners(self):
        self.check_singleton()
        if self.mode != "selected":
            return self.env["res.partner"]
        domains = []
        if self.customer_ids:
            domains.append(Domain("id", "in", self.customer_ids.ids))
        if self.customer_tag_ids:
            domains.append(Domain("tag_ids", "in", self.customer_tag_ids.ids))
        return self.env["res.partner"].search(
            Domain.OR(domains) if domains else Domain.TRUE
        )

    @api.depends("program_type", "points_granted", "coupon_qty")
    def _compute_confirmation_message(self) -> None:
        self.confirmation_message = False
        for wizard in self:
            program_desc = dict(
                wizard._fields["program_type"]._description_selection(wizard.env)
            )
            wizard.confirmation_message = self.env._(
                "You're about to generate %(program_type)s with a value of %(value)s for %(customer_number)i customers",
                program_type=program_desc[wizard.program_type],
                value=wizard.points_granted,
                customer_number=wizard.coupon_qty,
            )

    @api.depends("customer_ids", "customer_tag_ids", "mode")
    def _compute_coupon_qty(self) -> None:
        for wizard in self:
            if wizard.mode == "selected":
                wizard.coupon_qty = len(wizard._get_partners())
            else:
                wizard.coupon_qty = wizard.coupon_qty or 0

    @api.depends("mode", "program_id")
    def _compute_will_send_mail(self) -> None:
        for wizard in self:
            wizard.will_send_mail = (
                wizard.mode == "selected"
                and "create"
                in wizard.program_id.mapped("communication_plan_ids.trigger")
            )

    def _prepare_coupon_vals(self, partner) -> ValuesType:
        self.check_singleton()
        return {
            "program_id": self.program_id.id,
            "points": self.points_granted,
            "expiration_date": self.valid_until,
            "partner_id": partner.id if partner else False,
        }

    def generate_coupons(self):
        if any(not wizard.program_id for wizard in self):
            raise ValidationError(
                self.env._("Can not generate coupon, no program is set.")
            )
        if any(wizard.coupon_qty <= 0 for wizard in self):
            raise ValidationError(self.env._("Invalid quantity."))
        coupon_create_vals = []
        issuers = []
        for wizard in self:
            holders = (
                wizard._get_partners()
                if wizard.mode == "selected"
                else [self.env["res.partner"]] * wizard.coupon_qty
            )
            if not holders:
                continue
            coupon_create_vals.extend(
                wizard._prepare_coupon_vals(partner) for partner in holders
            )
            issuers.extend([wizard] * len(holders))
        coupons = self.env["loyalty.card"].create(coupon_create_vals)
        self.env["loyalty.history"].create(
            [
                {
                    "description": wizard.description
                    or self.env._("Gift For Customer"),
                    "card_id": coupon.id,
                    "issued": wizard.points_granted,
                }
                for coupon, wizard in zip(coupons, issuers, strict=True)
            ]
        )
        return coupons
