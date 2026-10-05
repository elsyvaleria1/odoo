from odoo import api, models


class ResourceResource(models.Model):
    _inherit = "resource.resource"

    @api.depends("product_id", "license_plate", "vin_sn", "name", "kind_id")
    def _compute_display_name(self):
        vehicles = self.filtered(lambda resource: resource.kind_code == "vehicle")
        for vehicle in vehicles:
            parts = [
                part
                for part in (
                    vehicle.product_id.manufacturer_id.name,
                    vehicle.product_id.name,
                )
                if part
            ]
            parts.append(vehicle._get_display_identity())
            vehicle.display_name = " / ".join(parts)
        super(ResourceResource, self - vehicles)._compute_display_name()

    def _get_display_identity(self):
        """What names this unit among others of its model. A plate is how a
        vehicle is spoken about, but one waiting for its paperwork has none --
        and a serial says more about which vehicle this is than "No Plate"
        does."""
        self.check_singleton()
        if self.license_plate or self.vin_sn:
            return self.license_plate or self.vin_sn
        # The asset's own name is composed from its model and its serial, and
        # the model is already the part before this one -- the same reason the
        # plate is not appended to a label that ends in it.
        name = self.name or ""
        model = self.product_id.name or ""
        if model and name.startswith(f"{model} "):
            name = name[len(model) + 1 :]
        return name or self.env._("No Plate")

    # a vehicle's product fills the model year when the vehicle has none
    @api.onchange("product_id")
    def _onchange_product_id_model_year(self) -> None:
        if not self.model_year and self.product_id.vehicle_model_year:
            self.model_year = int(self.product_id.vehicle_model_year)

    @api.model_create_multi
    def create(self, vals_list):
        products = self.env["product.product"].browse(
            [vals["product_id"] for vals in vals_list if vals.get("product_id")]
        )
        years = {
            product.id: int(product.vehicle_model_year)
            for product in products
            if product.vehicle_model_year
        }
        for vals in vals_list:
            if not vals.get("model_year") and vals.get("product_id") in years:
                vals["model_year"] = years[vals["product_id"]]
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if "product_id" in vals and "model_year" not in vals:
            for resource in self:
                if not resource.model_year and resource.product_id.vehicle_model_year:
                    resource.model_year = int(resource.product_id.vehicle_model_year)
        return res
