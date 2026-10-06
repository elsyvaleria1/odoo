from lxml import etree

from odoo.tests.common import TransactionCase

from .common import create_test_template


class TestDocumentsDocument(TransactionCase):
    def setUp(self):
        super().setUp()

        self.document_model = self.env["document.document"]
        self.stock_lot_model = self.env["product.trace"]
        self.product_template_model = self.env["product.template"]

        self.vehicle_product = create_test_template(
            self.env,
            name="Test Vehicle",
            asset_kind="vehicle",
            tracking="serial",
        )

        self.vehicle_lot = self.stock_lot_model.create(
            {
                "name": "VEH-TEST-001",
                "product_id": self.vehicle_product.product_variant_id.id,
            }
        )

        self.test_folder = self.env["document.document"].create(
            {
                "name": "Test Folder",
                "type": "folder",
            }
        )

    def test_asset_id_computed_when_linked(self):
        document = self.document_model.create(
            {
                "name": "Test Document",
                "res_model": "resource.asset",
                "res_id": self.vehicle_lot.asset_id.id,
                "folder_id": self.test_folder.id,
            }
        )

        self.assertEqual(
            document.asset_id,
            self.vehicle_lot.asset_id,
            "asset_id should be the asset the document is attached to",
        )

    def test_asset_id_computed_when_not_linked(self):
        document = self.document_model.create(
            {
                "name": "Test Document",
                "res_model": "res.partner",
                "res_id": 1,
                "folder_id": self.test_folder.id,
            }
        )

        self.assertFalse(
            document.asset_id,
            "asset_id should be False when not linked to product.trace",
        )

    def test_asset_id_computed_when_no_res_model(self):
        document = self.document_model.create(
            {
                "name": "Test Document",
                "folder_id": self.test_folder.id,
            }
        )

        self.assertFalse(
            document.asset_id,
            "asset_id should be False when document has no res_model",
        )

    def test_search_asset_id_by_id(self):
        document = self.document_model.create(
            {
                "name": "Test Document",
                "res_model": "resource.asset",
                "res_id": self.vehicle_lot.asset_id.id,
                "folder_id": self.test_folder.id,
            }
        )

        found_documents = self.document_model.search(
            [("asset_id", "in", [self.vehicle_lot.asset_id.id])]
        )

        self.assertIn(
            document,
            found_documents,
            "Should find document when searching by asset_id with integer ID",
        )

    def test_search_asset_id_by_name(self):
        document = self.document_model.create(
            {
                "name": "Test Document",
                "res_model": "resource.asset",
                "res_id": self.vehicle_lot.asset_id.id,
                "folder_id": self.test_folder.id,
            }
        )

        found_documents = self.document_model.search(
            [("asset_id", "ilike", "VEH-TEST")]
        )

        self.assertIn(
            document,
            found_documents,
            "Should find document when searching by asset_id with name pattern",
        )

    def test_search_asset_id_empty(self):
        document_without_lot = self.document_model.create(
            {
                "name": "Test Document Without Lot",
                "folder_id": self.test_folder.id,
            }
        )

        document_with_lot = self.document_model.create(
            {
                "name": "Test Document With Lot",
                "res_model": "resource.asset",
                "res_id": self.vehicle_lot.asset_id.id,
                "folder_id": self.test_folder.id,
            }
        )

        found_documents = self.document_model.search([("asset_id", "in", [False])])

        self.assertIn(
            document_without_lot,
            found_documents,
            "Should find document without asset_id when searching for False",
        )
        self.assertNotIn(
            document_with_lot,
            found_documents,
            "Should not find document with asset_id when searching for False",
        )

    def test_multiple_documents_same_lot(self):
        document1 = self.document_model.create(
            {
                "name": "Document 1",
                "res_model": "resource.asset",
                "res_id": self.vehicle_lot.asset_id.id,
                "folder_id": self.test_folder.id,
            }
        )

        document2 = self.document_model.create(
            {
                "name": "Document 2",
                "res_model": "resource.asset",
                "res_id": self.vehicle_lot.asset_id.id,
                "folder_id": self.test_folder.id,
            }
        )

        self.assertEqual(document1.asset_id, self.vehicle_lot.asset_id)
        self.assertEqual(document2.asset_id, self.vehicle_lot.asset_id)

        found_documents = self.document_model.search(
            [("asset_id", "=", self.vehicle_lot.asset_id.id)]
        )

        self.assertEqual(
            len(found_documents),
            2,
            "Should find both documents linked to the same lot",
        )

    def test_asset_id_in_search_view(self):
        arch = etree.fromstring(
            self.document_model.get_view(view_id=False, view_type="search")["arch"]
        )

        self.assertTrue(
            arch.xpath("//field[@name='asset_id']"),
            "the Documents search view should offer the asset field",
        )

    def test_search_asset_id_domain_shapes(self):
        linked = self.document_model.create(
            {
                "name": "Linked Document",
                "res_model": "resource.asset",
                "res_id": self.vehicle_lot.asset_id.id,
                "folder_id": self.test_folder.id,
            }
        )
        other_model = self.document_model.create(
            {
                "name": "Partner Document",
                "res_model": "res.partner",
                "res_id": 1,
                "folder_id": self.test_folder.id,
            }
        )
        unlinked = self.document_model.create(
            {
                "name": "Unlinked Document",
                "folder_id": self.test_folder.id,
            }
        )
        asset_id = self.vehicle_lot.asset_id.id

        finds_linked_only = [
            [("asset_id", "in", [asset_id])],
            [("asset_id", "=", asset_id)],
            [("asset_id", "in", [self.vehicle_lot.asset_id.name])],
            [("asset_id", "ilike", "VEH-TEST")],
            [("asset_id", "like", self.vehicle_lot.asset_id.name)],
            [("asset_id", "any", [("name", "=", self.vehicle_lot.asset_id.name)])],
            [("asset_id", "!=", False)],
            [("asset_id", "not in", [False])],
        ]
        for domain in finds_linked_only:
            with self.subTest(domain=domain):
                found = self.document_model.search(domain)
                self.assertIn(linked, found)
                self.assertNotIn(other_model, found)
                self.assertNotIn(unlinked, found)

        finds_everything_else = [
            [("asset_id", "in", [False])],
            [("asset_id", "=", False)],
        ]
        for domain in finds_everything_else:
            with self.subTest(domain=domain):
                found = self.document_model.search(domain)
                self.assertNotIn(linked, found)
                self.assertIn(other_model, found)
                self.assertIn(unlinked, found)

        negated = self.document_model.search([("asset_id", "not in", [asset_id])])
        self.assertNotIn(linked, negated)
        self.assertIn(unlinked, negated)

    def test_search_asset_id_accepts_a_plain_list(self):
        linked = self.document_model.create(
            {
                "name": "Linked Document",
                "res_model": "resource.asset",
                "res_id": self.vehicle_lot.asset_id.id,
                "folder_id": self.test_folder.id,
            }
        )
        domain = self.document_model._search_asset_id(
            "in", [self.vehicle_lot.asset_id.id]
        )
        self.assertIn(linked, self.document_model.search(domain))

    def test_search_asset_id_does_not_confuse_id_1_with_true(self):
        for_id_one = self.document_model._search_asset_id("in", [1])
        for_true = self.document_model._search_asset_id("in", [True])

        self.assertNotEqual(
            repr(for_id_one),
            repr(for_true),
            "searching lot id 1 must not resolve to the 'any lot' domain",
        )
        self.assertIn(
            "res_model",
            repr(for_id_one),
            "an id search resolves through res_model/res_id",
        )

    def test_search_asset_id_sentinels_still_work(self):
        linked = self.document_model.create(
            {
                "name": "Linked Document",
                "res_model": "resource.asset",
                "res_id": self.vehicle_lot.asset_id.id,
                "folder_id": self.test_folder.id,
            }
        )
        unlinked = self.document_model.create(
            {"name": "Unlinked Document", "folder_id": self.test_folder.id}
        )

        any_lot = self.document_model.search([("asset_id", "in", [True])])
        self.assertIn(linked, any_lot)
        self.assertNotIn(unlinked, any_lot)

        no_lot = self.document_model.search([("asset_id", "in", [False])])
        self.assertNotIn(linked, no_lot)
        self.assertIn(unlinked, no_lot)

        either = self.document_model.search([("asset_id", "in", [True, False])])
        self.assertIn(linked, either)
        self.assertIn(unlinked, either)

    def test_search_asset_id_mixes_a_sentinel_with_an_id(self):
        linked = self.document_model.create(
            {
                "name": "Linked Document",
                "res_model": "resource.asset",
                "res_id": self.vehicle_lot.asset_id.id,
                "folder_id": self.test_folder.id,
            }
        )
        unlinked = self.document_model.create(
            {"name": "Unlinked Document", "folder_id": self.test_folder.id}
        )

        found = self.document_model.search(
            [("asset_id", "in", [False, self.vehicle_lot.asset_id.id])]
        )

        self.assertIn(linked, found, "the id half must still match")
        self.assertIn(unlinked, found, "the False half must still match")
