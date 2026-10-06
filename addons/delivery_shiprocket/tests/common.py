from odoo.addons.delivery.tests.common import DeliveryCommon


class ShiprocketCommon(DeliveryCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.shiprocket = cls.env.ref("delivery_shiprocket.delivery_carrier_shiprocket")
