from lxml import etree

from odoo.tests import common


class TestMapLabels(common.TransactionCase):
    """What the live map writes on a marker when nothing knows better.

    This layer draws devices, points and parcels; it has never heard of a
    vehicle or a driver. A bridge that has overrides these -- see
    asset_gps_geoengine. Everything below is the floor that
    override falls back to, and the reason the marker is never blank.
    """

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
        # Nothing stores these, so a rename is on the map at the next read.
        # A stored value here would need a depends and a migration; the map
        # asks for at most a few dozen markers, so it never earned one.
        self.assertFalse(self.env["device.device"]._fields["map_title"].store)
        self.assertFalse(self.env["device.device"]._fields["map_subtitle"].store)
        self.device.name = "GPS-LABEL-01-RENAMED"
        self.assertEqual(self.device.map_title, "GPS-LABEL-01-RENAMED")

    def test_the_map_arch_still_asks_for_both_labels(self):
        # get_views only sends the fields the arch names, so a marker whose
        # template reads a field the <geoengine> node dropped renders blank.
        arch = etree.fromstring(
            self.env["device.device"].get_view(
                self.env.ref("device_gps_geoengine.view_device_device_geoengine").id,
                "geoengine",
            )["arch"]
        )
        named = set(arch.xpath("//geoengine/field/@name"))
        self.assertLessEqual({"name", "map_title", "map_subtitle"}, named)
