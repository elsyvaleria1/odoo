from odoo import fields, models


class WizardDeliveryCarrierUpdateSendcloudProduct(models.TransientModel):
    _name = "wizard.delivery.carrier.update.sendcloud.product"

    _description = "Choose from the available sendcloud shipping methods"

    carrier_id = fields.Many2one(
        comodel_name="delivery.carrier",
        string="Delivery",
    )

    shipping_products = fields.Json()
    return_products = fields.Json()

    # Using a Json rather than 2 Char fields allow us to work on reference from owl,
    # such allowing update of value on the same object client-side and server-side
    sendcloud_products_code = fields.Json(string="Active Products Code")

    def action_validate(self):
        active_shipping_product = next(
            (
                p
                for p in self.shipping_products
                if p["code"] == self.sendcloud_products_code["shipping"]
            ),
            self.shipping_products[0],
        )
        active_return_product = next(
            (
                p
                for p in self.return_products
                if p["code"] and p["code"] == self.sendcloud_products_code["return"]
            ),
            False,
        )
        self.carrier_id._set_sendcloud_products(
            active_shipping_product, active_return_product
        )
