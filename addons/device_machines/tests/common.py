from datetime import UTC, datetime

from odoo.addons.device.tests.common import DeviceTransactionCase


class DeviceMachinesCommon(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.config = cls.env["device.profile"].create({"name": "PLC Test Config"})
        cls.counter_category = cls.env.ref("device_machines.category_counter_plc")
        cls.device = cls._make_counter_device("Llenadora", "Llenadora")

    @classmethod
    def _make_counter_device(cls, name, identifier, **vals):
        values = {
            "name": name,
            "identifier": identifier,
            "config_id": cls.config.id,
            "comm_protocol": "mqtt",
            "endpoint": "iot.example.com",
            "company_id": cls.company.id,
            "device_category_id": cls.counter_category.id,
        }
        values.update(vals)
        return cls.env["device.device"].create(values)

    def _reading(self, device, when, count):
        bucket = self.env["device.machine.bucket"]._apply_reading(device, when, count)
        self.env["device.machine.reading"]._record(device, when, count)
        device.last_count = count
        return bucket

    def _create_counter(self, device, count=0, when=None):
        stamp = when or datetime(2026, 6, 18, 0, 0, 0, tzinfo=UTC)
        device.last_count = count
        self.env["device.machine.reading"]._record(device, stamp, count)
