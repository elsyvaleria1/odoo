from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    use_expiration_date = fields.Boolean(
        compute="_compute_use_expiration_date",
        store=True,
        readonly=False,
        help="When this box is ticked, you have the possibility to specify dates to manage"
        " product expiration, on the product and on the corresponding lot/serial numbers."
        " Defaults to the product category setting.",
    )
    expiration_time = fields.Integer(
        string="Expiration Date",
        help="Number of days after the receipt of the products (from the vendor"
        " or in stock after production) after which the goods may become dangerous"
        " and must not be consumed. It will be computed on the lot/serial number.",
    )
    use_time = fields.Integer(
        string="Best Before Date",
        help="Number of days before the Expiration Date after which the goods starts"
        " deteriorating, without being dangerous yet. It will be computed on the lot/serial number.",
    )
    removal_time = fields.Integer(
        string="Removal Date",
        help="Number of days before the Expiration Date after which the goods"
        " should be removed from the stock and not be counted in the Fresh On Hand Stock anymore."
        "It will be computed on the lot/serial number.",
    )
    alert_time = fields.Integer(
        string="Alert Date",
        help="Number of days before the Expiration Date after which an alert should be"
        " raised on the lot/serial number. It will be computed on the lot/serial number.",
    )

    @api.constrains("expiration_time", "use_time", "removal_time", "alert_time")
    def _check_expiry_times(self) -> None:
        for template in self:
            offsets = {
                self.env._("Expiration Date"): template.expiration_time,
                self.env._("Best Before Date"): template.use_time,
                self.env._("Removal Date"): template.removal_time,
                self.env._("Alert Date"): template.alert_time,
            }
            negative = [name for name, days in offsets.items() if days < 0]
            if negative:
                raise ValidationError(
                    self.env._(
                        "The expiry delays of %(product)s are numbers of days and cannot"
                        " be negative: %(fields)s. A negative delay puts a lot's removal"
                        " date after its expiration date, which leaves expired goods"
                        " reservable and blocks the transfer that would clear them.",
                        product=template.display_name,
                        fields=", ".join(negative),
                    )
                )

    @api.depends("categ_id.use_expiration_date")
    def _compute_use_expiration_date(self) -> None:
        for product in self:
            product.use_expiration_date = (
                product.tracking != "none" and product.categ_id.use_expiration_date
            )

    def write(self, vals):
        if vals.get("tracking") == "none":
            vals["use_expiration_date"] = False
            reactivated = self.browse()
        elif (
            vals.get("tracking") not in (None, "none")
            and "use_expiration_date" not in vals
        ):
            reactivated = self.filtered(lambda p: p.tracking == "none")
        else:
            reactivated = self.browse()
        result = super().write(vals)
        if reactivated:
            self.env.add_to_compute(self._fields["use_expiration_date"], reactivated)
        return result
