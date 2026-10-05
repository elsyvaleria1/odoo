from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import create_test_template


@tagged("post_install", "-at_install")
class TestLogProvenance(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        template = create_test_template(
            cls.env,
            name="Provenance probe truck",
            asset_kind="vehicle",
            tracking="serial",
        )
        cls.asset = cls.env["product.trace"].create(
            {
                "name": "PROV-1",
                "product_id": template.product_variant_ids[0].id,
                "license_plate": "PROV-1",
            }
        )

    def _sources(self):
        field = self.env["resource.log"]._fields["source"]
        return dict(field.get_description(self.env)["selection"])

    def test_a_hand_written_log_says_it_was_hand_written(self):
        log = self.env["resource.log"].create({"asset_id": self.asset.asset_id.id})
        self.assertEqual(log.source, "manual")

    def test_every_declared_source_has_a_label(self):
        for key, label in self._sources().items():
            self.assertTrue(label, f"source {key!r} carries no label")

    def test_a_source_exists_only_where_a_producer_writes_it(self):
        # Each producing module adds its own value through selection_add, so an
        # unwritten value is a vocabulary that outlived its producer.
        producers = {
            "manual": "resource_asset_product",
            "bill": "resource_asset_account",
            "gps": "asset_gps",
            "maintenance": "maintenance_stock",
            "toll": "web_scraper_highway",
            "approval": "approval_stock",
            "delivery": "stock_fleet",
            "assignment": "asset_ledger_hr",
            "import": "marin",
            "efectivale": "marin",
        }
        installed = set(
            self.env["ir.module.module"]
            .sudo()
            .search([("state", "=", "installed")])
            .mapped("name")
        )
        for key in self._sources():
            self.assertIn(
                key, producers, f"source {key!r} is declared by no known producer"
            )
            self.assertIn(
                producers[key],
                installed,
                f"source {key!r} is offered but {producers[key]} is not installed",
            )
