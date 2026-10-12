from lxml import etree

from odoo.tests import common


class TestMapLabels(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env["device.profile"].create({"name": "Map Label Config"})
        cls.device = cls.env["device.device"].create(
            {
                "name": "GPS-LABEL-01",
                "identifier": "GPS-LABEL-01",
                "config_id": cls.config.id,
                "comm_protocol": "http",
                "endpoint": "10.0.0.11",
                "is_gps_device": True,
            }
        )

    def test_a_device_the_layer_knows_nothing_else_about_is_its_own_name(self):
        self.assertEqual(self.device.map_title, self.device.name)
        self.assertFalse(self.device.map_subtitle)

    def test_the_labels_are_read_from_the_record_every_time(self):
        self.assertFalse(self.env["device.device"]._fields["map_title"].store)
        self.assertFalse(self.env["device.device"]._fields["map_subtitle"].store)
        self.device.name = "GPS-LABEL-01-RENAMED"
        self.assertEqual(self.device.map_title, "GPS-LABEL-01-RENAMED")

    def test_the_map_arch_still_asks_for_both_labels(self):
        arch = etree.fromstring(
            self.env["device.device"].get_view(
                self.env.ref("device_gps_geoengine.view_device_device_geoengine").id,
                "geoengine",
            )["arch"]
        )
        named = set(arch.xpath("//geoengine/field/@name"))
        self.assertLessEqual({"name", "map_title", "map_subtitle"}, named)
