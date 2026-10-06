from odoo import fields, models


class MixinTenderWarning(models.AbstractModel):
    _name = "mixin.tender.warning"
    _description = "Confirming one offer of a tender while others are open"

    order_ids = fields.Many2many(
        comodel_name="mixin.order.tender",
        relation="mixin_tender_warning_order_rel",
        string="Offers to Confirm",
    )
    rival_ids = fields.Many2many(
        comodel_name="mixin.order.tender",
        relation="mixin_tender_warning_rival_rel",
        string="Other Open Offers",
    )

    def action_keep_rivals(self):
        return self._confirm()

    def action_reject_rivals(self):
        self.rival_ids.filtered(
            lambda order: order.state == "draft" and order not in self.order_ids
        )._close_as(
            "rejected",
            note=self.env._(
                "Another offer of %(tender)s was confirmed.",
                tender=self.order_ids.tender_id[:1].name,
            ),
        )
        return self._confirm()

    def _confirm(self):
        return self.order_ids.with_context(skip_tender_check=True).action_confirm()
