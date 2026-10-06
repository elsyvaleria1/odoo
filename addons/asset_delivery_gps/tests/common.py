from unittest.mock import patch

from odoo import fields
from odoo.tests.common import TransactionCase

from odoo.addons.asset_ledger.tests.common import create_test_product


class GpsBridgeCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )

        cls.km_uom = cls.env.ref("uom.product_uom_km", raise_if_not_found=False)
        if not cls.km_uom:
            cls.km_uom = cls.env["uom.uom"].create(
                {
                    "name": "km",
                    "relative_factor": 1000,
                    "relative_uom_id": cls.env.ref("uom.product_uom_meter").id,
                }
            )

        cls.vehicle_product = create_test_product(
            cls.env,
            name="GPS Bridge Vehicle",
            type="consu",
            is_storable=True,
            tracking="serial",
            asset_kind="vehicle",
        )
        cls.config = cls.env["device.profile"].create(
            {
                "name": "GPS Bridge Config",
                "auth_type": "bearer",
                "auth_token": "gps_bridge_token",
                "reports_odometer": True,
                "odometer_correction_factor": 1.0,
            }
        )
        cls.device = cls.env["device.device"].create(
            {
                "name": "GPS Bridge Device",
                "identifier": "GPS-BRIDGE-0001",
                "credential_id": False,
                "config_id": cls.config.id,
                "company_id": cls.company.id,
                "comm_protocol": "http",
            }
        )
        # the vehicle carried its tracker long before the readings the tests
        # write: a reading counts from the device's attachment on
        attached = fields.Datetime.subtract(fields.Datetime.now(), days=800)
        with patch.object(fields.Datetime, "now", lambda: attached):
            cls.vehicle = cls.env["product.trace"].create(
                {
                    "name": "GPS-BRIDGE-VH",
                    "product_id": cls.vehicle_product.id,
                    "company_id": cls.company.id,
                    "odometer_uom_id": cls.km_uom.id,
                    "gps_device_id": cls.device.id,
                }
            )
        cls.asset = cls.vehicle.asset_id

    def gps_log(self, odometer, days_ago=0, valid=True, fuel_level=50.0, minutes_ago=0):
        return self.env["device.data.log.gps"].create(
            {
                "device_id": self.device.id,
                "timestamp": fields.Datetime.subtract(
                    fields.Datetime.now(), days=days_ago, minutes=minutes_ago
                ),
                "latitude": 20.6736,
                "longitude": -103.3440,
                "odometer": odometer,
                "odometer_valid": valid,
                "fuel_level": fuel_level,
            }
        )
