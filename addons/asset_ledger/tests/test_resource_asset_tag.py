from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestResourceAssetTag(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Tag = cls.env["resource.tag"]
        cls.urgent, cls.leased = cls.Tag.create(
            [{"name": "Urgent"}, {"name": "Leased"}]
        )

    def _asset(self, kind, name):
        return self.env["resource.resource"].create(
            {"name": name, "kind_id": self.env.ref(f"base.kind_{kind}").id}
        )

    def test_tags_through_the_root_reach_every_kind(self):
        tool = self._asset("tool", "Drill")
        vehicle = self._asset("vehicle", "Pickup")
        (tool | vehicle).asset_tag_ids = self.urgent
        vehicle.asset_tag_ids |= self.leased

        self.env.invalidate_all()
        self.assertEqual(tool.asset_tag_ids, self.urgent)
        self.assertEqual(vehicle.asset_tag_ids, self.urgent | self.leased)
        self.assertEqual(
            self.env["resource.resource"].search(
                [("asset_tag_ids", "in", self.leased.ids)]
            ),
            vehicle,
        )

    def test_asset_tags_leave_fleet_tags_alone(self):
        vehicle = self._asset("vehicle", "Truck")
        vehicle.asset_tag_ids = self.urgent

        self.env.invalidate_all()
        concrete = self.env["resource.asset.vehicle"].browse(vehicle.id)
        self.assertEqual(concrete.asset_tag_ids, self.urgent)
        self.assertFalse(concrete.tag_ids)

    def test_unlinking_an_asset_drops_its_tag_links(self):
        tool = self._asset("tool", "Saw")
        tool.asset_tag_ids = self.urgent
        tool.unlink()

        self.env.flush_all()
        self.env.cr.execute(
            "SELECT count(*) FROM resource_asset_tag_rel WHERE asset_id = %s",
            [tool.id],
        )
        self.assertEqual(self.env.cr.fetchone()[0], 0)
