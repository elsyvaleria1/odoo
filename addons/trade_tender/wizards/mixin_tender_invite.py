from odoo import Command, fields, models
from odoo.tools import clean_context


class MixinTenderInvite(models.AbstractModel):
    _name = "mixin.tender.invite"
    _description = "Invite counterparties to a tender"

    origin_order_id = fields.Many2one(
        comodel_name="mixin.order.tender",
        string="Origin",
        help="The offer the invited counterparties are asked to match.",
    )
    tender_id = fields.Many2one(
        comodel_name="mixin.tender",
        string="Tender",
        help="The tender whose needs the invited counterparties are asked to offer on.",
    )
    partner_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Invited",
        required=True,
        help="Each invited counterparty receives its own offer to fill in.",
    )
    copy_products = fields.Boolean(
        default=True,
        help="Start every invited offer from the origin's lines, or from the "
        "tender's needs.",
    )

    def _get_order_model(self):
        return self.env[self._fields["origin_order_id"].comodel_name]

    def action_invite(self):
        self.check_singleton()
        context = clean_context(self.env.context)
        if self.origin_order_id:
            context["tender_origin_id"] = self.origin_order_id.id
        offers = (
            self._get_order_model()
            .with_context(context)
            .create(self._prepare_offer_values())
        )
        self._on_offers_created(offers)
        action = {
            "type": "ir.actions.act_window",
            "res_model": offers._name,
            "view_mode": "list,form",
        }
        if len(offers) == 1:
            action.update(res_id=offers.id, view_mode="form")
        else:
            action.update(
                name=self.env._("Invited Offers"),
                domain=[("id", "in", offers.ids)],
            )
        return action

    def _on_offers_created(self, offers) -> None:
        return None

    def _prepare_offer_values(self):
        if not self.origin_order_id:
            return self._prepare_offer_values_from_tender()
        origin = self.origin_order_id
        return [
            {
                "partner_id": partner.id,
                "date_order": origin.date_order,
                "user_id": origin.user_id.id,
                "origin": origin.origin,
                **(
                    {
                        "line_ids": [
                            Command.create(
                                self._prepare_offer_line_values(line, partner)
                            )
                            for line in origin.line_ids
                        ]
                    }
                    if self.copy_products
                    else {}
                ),
            }
            for partner in self.partner_ids
        ]

    def _prepare_offer_values_from_tender(self) -> list:
        tender = self.tender_id
        return [
            {
                "partner_id": partner.id,
                "tender_id": tender.id,
                "company_id": tender.company_id.id,
                "user_id": tender.user_id.id,
                "origin": tender.name,
                **(
                    {
                        "line_ids": [
                            Command.create(need._prepare_offer_line_values())
                            for need in tender.line_ids
                        ]
                    }
                    if self.copy_products
                    else {}
                ),
            }
            for partner in self.partner_ids
        ]

    def _prepare_offer_line_values(self, line, partner):
        values = {
            "product_id": line.product_id.id,
            "product_qty": line.product_qty,
            "product_uom_id": line.product_uom_id.id,
            "display_type": line.display_type,
            "analytic_distribution": line.analytic_distribution,
        }
        if line.display_type:
            values["name"] = line.name
        return values
