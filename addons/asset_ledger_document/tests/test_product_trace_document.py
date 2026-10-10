import base64

from odoo import Command
from odoo.tests.common import TransactionCase

from ..models.resource_resource import DOCUMENT_LINKS
from .common import create_test_template


class TestStockLotDocuments(TransactionCase):
    def _set_kind_documents(self, kind_xmlid, folder=None, tags=None, centralize=None):
        """The folder, tags and switch a kind of asset files its documents under."""
        kind = self.env.ref(kind_xmlid)
        setting = self.env["resource.kind.document"].search(
            [("kind_id", "=", kind.id), ("company_id", "=", self.company.id)], limit=1
        )
        if not setting:
            setting = self.env["resource.kind.document"].create(
                {"kind_id": kind.id, "company_id": self.company.id}
            )
        values = {}
        if folder is not None:
            values["folder_id"] = folder.id
        if tags is not None:
            values["tag_ids"] = [Command.set(tags.ids)]
        if centralize is not None:
            values["centralize"] = centralize
        if values:
            setting.write(values)
        self.env["resource.resource"].invalidate_model()
        return setting

    def setUp(self):
        super().setUp()

        self.product_trace = self.env["product.trace"]
        self.product_template = self.env["product.template"]
        self.product_product = self.env["product.product"]
        self.document = self.env["document.document"]
        self.company_model = self.env["res.company"]

        self.company = self.env.ref("base.main_company")

        self.folder_equipment = self.env.ref(
            "asset_ledger_document.document_folder_equipment"
        )
        self.folder_fleet = self.env.ref("asset_ledger_document.document_folder_fleet")
        self.folder_machinery = self.env.ref(
            "asset_ledger_document.document_folder_machinery"
        )
        self.folder_property = self.env.ref(
            "asset_ledger_document.document_folder_property"
        )

        self.vehicle_product = create_test_template(
            self.env,
            name="Test Vehicle",
            asset_kind="vehicle",
            tracking="serial",
        )
        self.property_product = create_test_template(
            self.env,
            name="Test Property",
            asset_kind="property",
            tracking="serial",
        )
        self.machinery_product = create_test_template(
            self.env,
            name="Test Machinery",
            asset_kind="machinery",
            tracking="serial",
        )
        self.equipment_product = create_test_template(
            self.env,
            name="Test Equipment",
            asset_kind="equipment",
            tracking="serial",
        )

    def test_documents_settings_computation_vehicle(self):
        vehicle_lot = self.product_trace.create(
            {
                "name": "VEH-001",
                "product_id": self.vehicle_product.product_variant_id.id,
                "company_id": self.company.id,
            }
        )

        self._set_kind_documents("resource.kind_vehicle", centralize=True)

        self.assertTrue(
            vehicle_lot.asset_id.document_centralized,
            "Vehicle should have documents enabled when fleet settings are True",
        )

    def test_documents_settings_computation_property(self):
        property_lot = self.product_trace.create(
            {
                "name": "PROP-001",
                "product_id": self.property_product.product_variant_id.id,
                "company_id": self.company.id,
            }
        )

        self._set_kind_documents("resource.kind_property", centralize=True)

        self.assertTrue(
            property_lot.asset_id.document_centralized,
            "Property should have documents enabled when property settings are True",
        )

    def test_documents_settings_computation_machinery(self):
        machinery_lot = self.product_trace.create(
            {
                "name": "MACH-001",
                "product_id": self.machinery_product.product_variant_id.id,
                "company_id": self.company.id,
            }
        )

        self._set_kind_documents("resource.kind_machinery", centralize=True)

        self.assertTrue(
            machinery_lot.asset_id.document_centralized,
            "Machinery should have documents enabled when machinery settings are True",
        )

    def test_documents_settings_computation_equipment(self):
        equipment_lot = self.product_trace.create(
            {
                "name": "EQUIP-001",
                "product_id": self.equipment_product.product_variant_id.id,
                "company_id": self.company.id,
            }
        )

        self._set_kind_documents("resource.kind_equipment", centralize=True)

        self.assertTrue(
            equipment_lot.asset_id.document_centralized,
            "Equipment should have documents enabled when equipment settings are True",
        )

    def test_get_document_folder_vehicle(self):
        vehicle_lot = self.product_trace.create(
            {
                "name": "VEH-002",
                "product_id": self.vehicle_product.product_variant_id.id,
                "company_id": self.company.id,
            }
        )

        self._set_kind_documents(
            "resource.kind_vehicle", folder=self.folder_fleet
        )

        folder = vehicle_lot.asset_id._get_document_folder()
        self.assertEqual(
            folder,
            self.folder_fleet,
            "Vehicle should use fleet folder",
        )

    def test_get_document_folder_property(self):
        property_lot = self.product_trace.create(
            {
                "name": "PROP-002",
                "product_id": self.property_product.product_variant_id.id,
                "company_id": self.company.id,
            }
        )

        self._set_kind_documents(
            "resource.kind_property", folder=self.folder_property
        )

        folder = property_lot.asset_id._get_document_folder()
        self.assertEqual(
            folder,
            self.folder_property,
            "Property should use property folder",
        )

    def test_get_document_folder_machinery(self):
        machinery_lot = self.product_trace.create(
            {
                "name": "MACH-002",
                "product_id": self.machinery_product.product_variant_id.id,
                "company_id": self.company.id,
            }
        )

        self._set_kind_documents(
            "resource.kind_machinery", folder=self.folder_machinery
        )

        folder = machinery_lot.asset_id._get_document_folder()
        self.assertEqual(
            folder,
            self.folder_machinery,
            "Machinery should use machinery folder",
        )

    def test_get_document_folder_equipment(self):
        equipment_lot = self.product_trace.create(
            {
                "name": "EQUIP-002",
                "product_id": self.equipment_product.product_variant_id.id,
                "company_id": self.company.id,
            }
        )

        self._set_kind_documents(
            "resource.kind_equipment", folder=self.folder_equipment
        )

        folder = equipment_lot.asset_id._get_document_folder()
        self.assertEqual(
            folder,
            self.folder_equipment,
            "Equipment should use equipment folder",
        )

    def test_get_document_owner(self):
        vehicle_lot = self.product_trace.create(
            {
                "name": "VEH-003",
                "product_id": self.vehicle_product.product_variant_id.id,
                "company_id": self.company.id,
            }
        )

        owner = vehicle_lot.asset_id._get_document_owner()
        self.assertEqual(
            owner,
            self.env.user,
            "Document owner should be current user",
        )

    def test_action_view_attachments(self):
        vehicle_lot = self.product_trace.create(
            {
                "name": "VEH-004",
                "product_id": self.vehicle_product.product_variant_id.id,
                "company_id": self.company.id,
            }
        )

        self._set_kind_documents("resource.kind_vehicle", centralize=True)
        self._set_kind_documents(
            "resource.kind_vehicle", folder=self.folder_fleet
        )

        action = vehicle_lot.action_view_documents()

        self.assertEqual(
            action["res_model"],
            "document.document",
            "Action should open documents",
        )
        self.assertEqual(
            action["context"]["searchpanel_default_user_folder_id"],
            str(self.folder_fleet.id),
            "the search panel reads user_folder_id, as a string",
        )
        self.assertNotIn(
            "searchpanel_default_folder_id",
            action["context"],
            "there is no folder_id field in the Documents search panel",
        )

    def test_check_create_documents_enabled(self):
        vehicle_lot = self.product_trace.create(
            {
                "name": "VEH-005",
                "product_id": self.vehicle_product.product_variant_id.id,
                "company_id": self.company.id,
            }
        )

        self._set_kind_documents("resource.kind_vehicle", centralize=True)

        can_create = vehicle_lot.asset_id._check_create_documents()
        self.assertTrue(
            can_create,
            "Should be able to create documents when fleet settings are enabled",
        )

    def test_check_create_documents_disabled(self):
        vehicle_lot = self.product_trace.create(
            {
                "name": "VEH-006",
                "product_id": self.vehicle_product.product_variant_id.id,
                "company_id": self.company.id,
            }
        )

        self._set_kind_documents("resource.kind_vehicle", centralize=False)

        can_create = vehicle_lot.asset_id._check_create_documents()
        self.assertFalse(
            can_create,
            "Should not be able to create documents when fleet settings are disabled",
        )

    def test_count_document_computation(self):
        vehicle_lot = self.product_trace.create(
            {
                "name": "VEH-007",
                "product_id": self.vehicle_product.product_variant_id.id,
                "company_id": self.company.id,
            }
        )

        self.document.create(
            {
                "name": "Test Document 1",
                "res_model": "resource.resource",
                "res_id": vehicle_lot.asset_id.id,
                "folder_id": self.folder_fleet.id,
            }
        )
        self.document.create(
            {
                "name": "Test Document 2",
                "res_model": "resource.resource",
                "res_id": vehicle_lot.asset_id.id,
                "folder_id": self.folder_fleet.id,
            }
        )

        self.assertEqual(
            vehicle_lot.asset_id.count_document,
            2,
            "Should count 2 documents linked to the lot",
        )

    def test_it_asset_and_tools_file_under_equipment(self):
        self._set_kind_documents(
            "resource.kind_equipment", folder=self.folder_equipment
        )
        for asset_kind in ("it", "tool"):
            with self.subTest(asset_kind=asset_kind):
                product = create_test_template(
                    self.env,
                    name=f"Test {asset_kind}",
                    asset_kind=asset_kind,
                    tracking="serial",
                )
                lot = self.product_trace.create(
                    {
                        "name": f"{asset_kind.upper()}-001",
                        "product_id": product.product_variant_id.id,
                        "company_id": self.company.id,
                    }
                )
                self.assertEqual(
                    lot.asset_id._get_document_folder(),
                    self.folder_equipment,
                    f"{asset_kind} should file under Equipment",
                )

    def test_company_less_lot_uses_active_company(self):
        self._set_kind_documents("resource.kind_vehicle", centralize=True)
        self._set_kind_documents(
            "resource.kind_vehicle", folder=self.folder_fleet
        )
        lot = self.product_trace.create(
            {
                "name": "VEH-NO-COMPANY",
                "product_id": self.vehicle_product.product_variant_id.id,
            }
        )
        lot.company_id = False

        self.assertFalse(lot.company_id, "the lot must really have no company")
        self.assertEqual(lot.asset_id._documents_company(), self.env.company)
        self.assertEqual(lot.asset_id._get_document_folder(), self.folder_fleet)
        self.assertTrue(lot.asset_id._check_create_documents())
        self.assertTrue(lot.asset_id.document_centralized)

    def test_documents_settings_follows_the_company_toggle(self):
        vehicle_lot = self.product_trace.create(
            {
                "name": "VEH-TOGGLE",
                "product_id": self.vehicle_product.product_variant_id.id,
                "company_id": self.company.id,
            }
        )
        self._set_kind_documents("resource.kind_vehicle", centralize=True)
        self.assertTrue(vehicle_lot.asset_id.document_centralized)

        self._set_kind_documents("resource.kind_vehicle", centralize=False)
        self.assertFalse(
            vehicle_lot.asset_id.document_centralized,
            "turning the fleet toggle off must hide the Documents button",
        )

        self._set_kind_documents("resource.kind_vehicle", centralize=True)
        self.assertTrue(
            vehicle_lot.asset_id.document_centralized,
            "turning it back on must show the button again",
        )

    def test_documents_settings_follows_the_asset_kind(self):
        tool_product = create_test_template(
            self.env, name="Test Tool", asset_kind="tool", tracking="serial"
        )
        tool_lot = self.product_trace.create(
            {
                "name": "TOOL-RETYPE",
                "product_id": tool_product.product_variant_id.id,
                "company_id": self.company.id,
            }
        )
        gauge = self.env["resource.kind"].create({"name": "Gauge", "code": "gauge"})
        self.env["resource.kind.document"].create(
            {"kind_id": gauge.id, "company_id": self.company.id, "centralize": True}
        )
        self._set_kind_documents("resource.kind_tool", centralize=False)
        self.assertFalse(tool_lot.asset_id.document_centralized)

        tool_lot.asset_id.kind_id = gauge
        self.assertTrue(
            tool_lot.asset_id.document_centralized,
            "the flag must follow the asset's kind",
        )

    def test_a_product_s_new_kind_leaves_its_assets_as_they_are(self):
        vehicle_lot = self.product_trace.create(
            {
                "name": "VEH-KEPT",
                "product_id": self.vehicle_product.product_variant_id.id,
                "company_id": self.company.id,
            }
        )
        self.vehicle_product.asset_kind_id = self.env.ref(
            "resource.kind_equipment"
        )
        self.assertEqual(
            vehicle_lot.asset_id.kind_id, self.env.ref("resource.kind_vehicle")
        )

    def test_count_document_follows_the_documents(self):
        vehicle_lot = self.product_trace.create(
            {
                "name": "VEH-COUNT",
                "product_id": self.vehicle_product.product_variant_id.id,
                "company_id": self.company.id,
            }
        )
        self.assertEqual(vehicle_lot.asset_id.count_document, 0)

        document = self.document.create(
            {
                "name": "Counted Document",
                "res_model": "resource.resource",
                "res_id": vehicle_lot.asset_id.id,
                "folder_id": self.folder_fleet.id,
            }
        )
        self.assertEqual(
            vehicle_lot.asset_id.count_document,
            1,
            "creating a document must bump the stat button",
        )

        document.unlink()
        self.assertEqual(
            vehicle_lot.asset_id.count_document,
            0,
            "deleting it must bring the stat button back down",
        )

    def test_fields_get_survives_a_deleted_tag(self):
        links = {
            "fuel_card_id": "asset_ledger_document.documents_tag_fuel_card",
            "highway_pass_id": "asset_ledger_document.documents_tag_highway_pass",
            "property_deed_id": "asset_ledger_document.documents_tag_property_deed",
            "lease_agreement_id": (
                "asset_ledger_document.documents_tag_lease_agreement"
            ),
            "building_permit_id": (
                "asset_ledger_document.documents_tag_building_permit"
            ),
        }
        for field_name, tag_xmlid in links.items():
            with self.subTest(field=field_name), self.env.cr.savepoint():
                self.env.ref(tag_xmlid).unlink()
                self.env.registry.clear_cache()

                described = self.env["resource.resource"].fields_get([field_name])
                self.assertEqual(
                    described[field_name]["domain"],
                    [(1, "=", 0)],
                    "a missing tag must match nothing, not raise",
                )
                self.env["resource.resource"].fields_get()

    def test_document_tag_domain_uses_the_tag_when_present(self):
        tag = self.env.ref("asset_ledger_document.documents_tag_fuel_card")
        self.assertEqual(
            self.env["resource.resource"].fields_get(["fuel_card_id"])["fuel_card_id"][
                "domain"
            ],
            [("tag_ids", "in", tag.ids)],
        )

    def _tagged_document(self, name, tag_xmlid):
        return self.document.create(
            {
                "name": name,
                "folder_id": self.folder_fleet.id,
                "tag_ids": [Command.set([self.env.ref(tag_xmlid).id])],
            }
        )

    def test_document_link_inverse_points_document_at_asset(self):
        lot = self.product_trace.create(
            {
                "name": "VEH-LINKS",
                "product_id": self.vehicle_product.product_variant_id.id,
                "company_id": self.company.id,
            }
        )
        for field_name, link in DOCUMENT_LINKS.items():
            with self.subTest(field=field_name):
                document = self._tagged_document(f"{field_name}.pdf", link.tag_xmlid)
                lot.write({field_name: document.id})

                self.assertEqual(document.res_model, "resource.resource")
                self.assertEqual(document.res_id, lot.asset_id.id)
                self.assertTrue(document.is_editable_attachment)

    def test_document_link_inverse_leaves_the_other_links_alone(self):
        lot = self.product_trace.create(
            {
                "name": "VEH-ONE-LINK",
                "product_id": self.vehicle_product.product_variant_id.id,
                "company_id": self.company.id,
            }
        )
        fuel = self._tagged_document(
            "Efecticard A1.pdf", DOCUMENT_LINKS["fuel_card_id"].tag_xmlid
        )
        pass_doc = self._tagged_document(
            "IMDM B2.pdf", DOCUMENT_LINKS["highway_pass_id"].tag_xmlid
        )
        lot.write({"fuel_card_id": fuel.id, "highway_pass_id": pass_doc.id})
        untouched_write_date = pass_doc.write_date

        pass_doc.invalidate_recordset()
        lot.write({"fuel_card_id": fuel.id})

        self.assertEqual(
            pass_doc.write_date,
            untouched_write_date,
            "writing fuel_card_id must not touch the highway pass document",
        )

    def test_document_link_name_strips_the_vendor_prefix(self):
        lot = self.product_trace.create(
            {
                "name": "VEH-NAMES",
                "product_id": self.vehicle_product.product_variant_id.id,
                "company_id": self.company.id,
            }
        )
        cases = {
            "fuel_card_id": ("Efecticard ABC123.pdf", "ABC123"),
            "highway_pass_id": ("IMDM XYZ789.pdf", "XYZ789"),
            "property_deed_id": ("Deed 2020.pdf", "Deed 2020"),
            "lease_agreement_id": ("Lease 2021.pdf", "Lease 2021"),
            "building_permit_id": ("Permit 2022.pdf", "Permit 2022"),
        }
        for field_name, (filename, expected) in cases.items():
            link = DOCUMENT_LINKS[field_name]
            with self.subTest(field=field_name):
                document = self._tagged_document(filename, link.tag_xmlid)
                lot.write({field_name: document.id})

                self.assertEqual(lot.asset_id[link.name_field], expected)

    def test_document_link_fields_keep_their_declaration(self):
        resource_model = self.env["resource.resource"]
        described = resource_model.fields_get(list(DOCUMENT_LINKS))
        for field_name in DOCUMENT_LINKS:
            field = resource_model._fields[field_name]
            with self.subTest(field=field_name):
                self.assertEqual(described[field_name]["type"], "many2one")
                self.assertEqual(described[field_name]["relation"], "document.document")
                self.assertTrue(field.store)
                self.assertFalse(field.readonly)
                self.assertEqual(field.inverse, "_inverse_document_links")
                self.assertEqual(field.compute, None)

    def _internal_user(self, login):
        return self.env["res.users"].create(
            {
                "name": login,
                "login": login,
                "company_id": self.company.id,
                "company_ids": [Command.set([self.company.id])],
                "group_ids": [
                    Command.set(
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("document.group_documents_user").id,
                            self.env.ref("stock.group_stock_manager").id,
                            # The document files on the asset, so attaching one
                            # takes the right to write the asset, not the serial.
                            self.env.ref("asset_ledger.group_enable_fleet_assets").id,
                        ]
                    )
                ],
            }
        )

    def test_auto_created_document_is_readable_by_colleagues(self):
        owner = self._internal_user("asset_doc_owner")
        colleague = self._internal_user("asset_doc_colleague")
        self._set_kind_documents("resource.kind_vehicle", centralize=True)
        self._set_kind_documents(
            "resource.kind_vehicle", folder=self.folder_fleet
        )

        lot = self.product_trace.create(
            {
                "name": "VEH-SHARED",
                "product_id": self.vehicle_product.product_variant_id.id,
                "company_id": self.company.id,
            }
        )
        attachment = (
            self.env["ir.attachment"]
            .with_user(owner)
            .create(
                {
                    "name": "shared.txt",
                    "res_model": "resource.resource",
                    "res_id": lot.asset_id.id,
                    "datas": base64.b64encode(b"shared"),
                }
            )
        )
        document = self.document.sudo().search([("attachment_id", "=", attachment.id)])

        self.assertTrue(document, "the mixin should have filed a document")
        self.assertEqual(document.folder_id, self.folder_fleet)
        self.assertEqual(document.access_internal, "view")
        self.assertEqual(document.access_via_link, "none")
        self.assertEqual(
            self.document.with_user(colleague).search_count([("id", "=", document.id)]),
            1,
            "a second internal user must be able to read the asset document",
        )

    def test_auto_created_document_carries_the_asset_tags(self):
        owner = self._internal_user("asset_tag_owner")
        self._set_kind_documents("resource.kind_vehicle", centralize=True)
        self._set_kind_documents(
            "resource.kind_vehicle", folder=self.folder_fleet
        )
        fleet_tag = self.env.ref("asset_ledger_document.documents_tag_fleet_doc")

        lot = self.product_trace.create(
            {
                "name": "VEH-TAGGED",
                "product_id": self.vehicle_product.product_variant_id.id,
                "company_id": self.company.id,
            }
        )
        attachment = (
            self.env["ir.attachment"]
            .with_user(owner)
            .create(
                {
                    "name": "tagged.txt",
                    "res_model": "resource.resource",
                    "res_id": lot.asset_id.id,
                    "datas": base64.b64encode(b"tagged"),
                }
            )
        )
        document = self.document.sudo().search([("attachment_id", "=", attachment.id)])

        self.assertTrue(document)
        self.assertIn(
            fleet_tag,
            document.tag_ids,
            "the manifest promises folder AND tags from the asset type",
        )
