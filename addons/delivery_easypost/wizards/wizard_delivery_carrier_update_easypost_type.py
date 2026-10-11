from odoo import fields, models


class WizardDeliveryCarrierUpdateEasypostType(models.TransientModel):
    _name = "wizard.delivery.carrier.update.easypost.type"
    _description = "Carrier Type"

    carrier_type = fields.Char()
    delivery_carrier_id = fields.Many2one(comodel_name="delivery.carrier")

    def action_validate(self):
        if self.delivery_carrier_id.easypost_delivery_type != self.carrier_type:
            self.delivery_carrier_id.easypost_delivery_type = self.carrier_type
            self.delivery_carrier_id.easypost_delivery_type_id = self.env.context[
                "carrier_types"
            ][self.carrier_type]

            self.delivery_carrier_id.easypost_delivery_type = self.carrier_type
            self.delivery_carrier_id.easypost_default_package_type_id = False
            self.delivery_carrier_id.easypost_default_service_id = False

        package_types_by_carriers, services_by_carriers = self.env[
            "delivery.carrier"
        ]._easypost_get_services_and_package_types()
        package_types = package_types_by_carriers.get(self.carrier_type)
        services = services_by_carriers.get(self.carrier_type)
        if package_types:
            already_existing_packages = self.env["stock.package.type"].search_read(
                [
                    ("package_carrier_type", "=", "easypost"),
                    ("easypost_carrier", "=", self.carrier_type),
                    ("shipper_package_code", "in", package_types),
                    ("name", "in", package_types),
                ],
                ["name"],
            )
            self.env["stock.package.type"].create(
                [
                    {
                        "name": package_type,
                        "package_carrier_type": "easypost",
                        "shipper_package_code": package_type,
                        "easypost_carrier": self.carrier_type,
                    }
                    for package_type in set(package_types)
                    ^ {package["name"] for package in already_existing_packages}
                ]
            )
        if services:
            already_existing_services = self.env["easypost.service"].search_read(
                [
                    ("easypost_carrier", "=", self.carrier_type),
                    ("name", "in", services),
                ],
                ["name"],
            )
            self.env["easypost.service"].create(
                [
                    {
                        "name": service,
                        "easypost_carrier": self.carrier_type,
                    }
                    for service in set(services)
                    ^ {service["name"] for service in already_existing_services}
                ]
            )
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "delivery.action_delivery_carrier_form"
        )
        action["res_id"] = self.delivery_carrier_id.id
        action["views"] = [
            (self.env.ref("delivery.view_delivery_carrier_form").id, "form")
        ]
        return action
