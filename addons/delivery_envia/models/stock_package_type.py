from odoo import api, fields, models
from odoo.exceptions import ValidationError


class StockPackageType(models.Model):
    _inherit = "stock.package.type"

    package_carrier_type = fields.Selection(selection_add=[("envia", "Envia")])
    shipper_package_code = fields.Char(
        compute="_compute_package_code",
        store=True,
        readonly=False,
    )
    envia_mail_type = fields.Selection(
        selection=[("pallet", "Pallet"), ("box", "Box"), ("envelope", "Envelope")],
        string="Envia Package Type",
        default="box",
        help="Select the package type for the shipment",
    )

    @api.depends("envia_mail_type", "package_carrier_type")
    def _compute_package_code(self) -> None:
        for package in self:
            if package.package_carrier_type == "envia":
                package.shipper_package_code = package.envia_mail_type
            else:
                package.shipper_package_code = package.shipper_package_code

    @api.constrains("packaging_length", "width", "height", "package_carrier_type")
    def _check_envia_required_value(self) -> None:
        for record in self:
            if record.package_carrier_type == "envia" and any(
                dim <= 0
                for dim in (record.packaging_length, record.width, record.height)
            ):
                raise ValidationError(
                    self.env._(
                        "Length, Width, and Height is necessary for a Envia Package."
                    )
                )

    @api.depends("package_carrier_type")
    def _compute_length_uom_name(self) -> None:
        super()._compute_length_uom_name()
        uom_name = (
            self.env["product.template"]._get_uom_from_setting("length").display_name
        )
        for package in self:
            if package.package_carrier_type == "envia":
                package.length_uom_name = uom_name
