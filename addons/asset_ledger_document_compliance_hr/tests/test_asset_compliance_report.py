from odoo.tests.common import TransactionCase


class TestAssetComplianceReportHrFields(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Report = cls.env["asset.compliance.report"]

    def test_report_has_asset_manager_field(self):
        field = self.Report._fields.get("asset_manager_id")

        self.assertIsNotNone(field, "asset_manager_id field must exist on the report")
        self.assertEqual(field.comodel_name, "hr.employee")

    def test_asset_manager_field_is_readonly(self):
        field = self.Report._fields.get("asset_manager_id")

        self.assertTrue(field.readonly)


class TestAssetComplianceReportHrRegistry(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Report = cls.env["asset.compliance.report"]

    def test_the_base_query_is_extended_not_replaced(self):
        base = self.env.registry["asset.compliance.report"]
        owners = {
            cls.__module__.split(".")[2]
            for cls in base.mro()
            if "_with_cte" in vars(cls) and cls.__module__.startswith("odoo.addons.")
        }
        self.assertIn("asset_ledger_document_compliance", owners)
        self.assertNotIn("asset_ledger_document_compliance_hr", owners)

    def test_the_report_names_the_live_manager(self):
        kind = self.env.ref("resource_asset.kind_vehicle")
        product = self.env["product.product"].create(
            {"name": "Managed Asset Model", "type": "consu", "asset_kind_id": kind.id}
        )
        asset = self.env["resource.asset"].create(
            {"name": "Managed Asset", "kind_id": kind.id, "product_id": product.id}
        )
        manager = self.env["hr.employee"].create({"name": "Asset Manager"})
        self.env["resource.assignment"].create(
            {
                "resource_id": asset.resource_id.id,
                "assignee_id": manager.resource_id.id,
                "custody_role": "manager",
            }
        )
        self.env["document.type"].create(
            {
                "name": "Managed asset papers",
                "code": "MANAGED_ASSET",
                "company_id": False,
                "is_mandatory": True,
                "applies_to": "resource.asset",
            }
        )
        self.env.flush_all()
        self.Report.refresh()

        row = self.Report.search([("asset_id", "=", asset.id)])

        self.assertEqual(row.asset_manager_id, manager)

    def test_select_preserves_parent_fields(self):
        fields = self.Report._get_fields_select()

        parent_keys = [
            "id",
            "entity_name",
            "product_tmpl_id",
            "product_name",
            "asset_kind_id",
            "asset_id",
            "asset_name",
            "location_id",
            "compliance_percentage",
            "company_id",
        ]
        for key in parent_keys:
            self.assertIn(
                key,
                fields,
                f"Parent SELECT field '{key}' must be preserved after HR extension",
            )

    def test_group_by_preserves_parent_fields(self):
        group_by = self.Report._get_fields_group_by()

        parent_fields = [
            "adt.product_tmpl_id",
            "adt.product_name",
            "adt.asset_kind_id",
            "adt.asset_id",
            "adt.asset_name",
            "adt.location_id",
            "adt.company_id",
        ]
        for field in parent_fields:
            self.assertIn(
                field,
                group_by,
                f"Parent GROUP BY field '{field}' must be preserved after HR extension",
            )
