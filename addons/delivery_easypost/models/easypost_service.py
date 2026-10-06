from odoo import fields, models


class EasypostService(models.Model):
    _name = "easypost.service"
    _description = "Easypost Service"

    name = fields.Char(
        string="Service Level Name",
        index=True,
    )
    easypost_carrier = fields.Char(
        string="Carrier Prefix",
        index=True,
    )

    def _require_residential_address(self) -> bool:
        services = [("FedEx", "GROUND_HOME_DELIVERY")]
        return (self.easypost_carrier, self.name) in services

    def _get_service_specific_options(self):
        options = {}
        if (self.easypost_carrier, self.name) == ("FedEx", "GROUND_HOME_DELIVERY"):
            options["saturday_delivery"] = False
        return options
