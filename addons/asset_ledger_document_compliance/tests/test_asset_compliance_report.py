from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestAssetComplianceReportFields(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.Report = cls.env["asset.compliance.report"]

    def test_report_model_exists(self):
        self.assertIn("asset.compliance.report", self.env)

    def test_report_inherits_document_compliance(self):
        children = self.env["document.compliance.report"]._inherit_children

        self.assertIn("asset.compliance.report", children)

    def test_the_report_names_the_kind_every_asset_already_has(self):
        field = self.Report._fields.get("asset_kind_id")

        self.assertIsNotNone(field)
        self.assertEqual(field.comodel_name, "resource.kind")

    def test_compliance_status_selection_values(self):
        field = self.Report._fields.get("compliance_status")

        self.assertIsNotNone(field)
        selection_keys = [s[0] for s in field.selection]
        self.assertIn("compliant", selection_keys)
        self.assertIn("partial", selection_keys)
        self.assertIn("non_compliant", selection_keys)
        self.assertIn("no_requirements", selection_keys)


class TestAssetComplianceReportQueryMethods(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Report = cls.env["asset.compliance.report"]

    def test_get_select_fields_returns_dict(self):
        result = self.Report._get_fields_select()

        self.assertIsInstance(result, dict)
        self.assertIn("product_tmpl_id", result)
        self.assertIn("product_name", result)
        self.assertIn("compliance_percentage", result)

    def test_get_from_tables_returns_list(self):
        result = self.Report._get_from_tables()

        self.assertIsInstance(result, list)
        self.assertTrue(len(result) > 0)

    def test_get_where_conditions_returns_list(self):
        result = self.Report._get_where_conditions()

        self.assertIsInstance(result, list)

    def test_get_group_by_fields_returns_list(self):
        result = self.Report._get_fields_group_by()

        self.assertIsInstance(result, list)
        self.assertIn("adt.product_tmpl_id", result)
        self.assertIn("adt.asset_id", result)


class TestAssetComplianceReportActions(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.Report = cls.env["asset.compliance.report"]

    def test_get_asset_compliance_by_kind_returns_list(self):
        result = self.Report.get_asset_compliance_by_kind()

        self.assertIsInstance(result, list)


class TestAssetRequirements(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Report = cls.env["asset.compliance.report"]
        cls.env["document.type"].search([("is_mandatory", "=", True)]).write(
            {"is_mandatory": False}
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Reported Asset Model",
                "type": "consu",
                "is_storable": True,
                "tracking": "serial",
                "asset_kind_id": cls.env.ref("base.kind_vehicle").id,
            }
        )
        cls.asset = cls.env["resource.resource"].create(
            {
                "name": "Reported Asset",
                "kind_id": cls.env.ref("base.kind_vehicle").id,
                "product_id": cls.product.id,
            }
        )

    def _type(self, code, applies_to):
        return self.env["document.type"].create(
            {
                "name": f"Type {code}",
                "code": code,
                "company_id": False,
                "is_mandatory": True,
                "applies_to": applies_to,
            }
        )

    def _total_required(self):
        self.env.flush_all()
        self.Report.refresh()
        self.env.invalidate_all()
        rows = self.Report.search([("asset_id", "=", self.asset.id)])
        return sum(rows.mapped("total_required"))

    def test_a_type_that_applies_to_assets_is_required_of_one(self):
        before = self._total_required()
        self._type("ASSET_SCOPED", "resource.resource")

        self.assertEqual(self._total_required(), before + 1)

    def test_a_type_that_applies_to_partners_is_not_required_of_an_asset(self):
        before = self._total_required()
        self._type("PARTNER_SCOPED", "res.partner")

        self.assertEqual(self._total_required(), before)

    def test_a_type_that_applies_to_everything_is_required_of_an_asset(self):
        before = self._total_required()
        self._type("EVERY_ENTITY", "all")

        self.assertEqual(self._total_required(), before + 1)


class TestAssetComplianceReportAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vehicle, cls.computer = cls.env["resource.resource"].create(
            [
                {
                    "name": f"Access {kind}",
                    "kind_id": cls.env.ref(f"resource.kind_{kind}").id,
                    "product_id": cls.env["product.product"]
                    .create(
                        {
                            "name": f"Access {kind} Model",
                            "type": "consu",
                            "is_storable": True,
                            "tracking": "serial",
                            "asset_kind_id": cls.env.ref(
                                f"resource.kind_{kind}"
                            ).id,
                        }
                    )
                    .id,
                }
                for kind in ("vehicle", "it")
            ]
        )
        cls.plain_user, cls.it_asset_user, cls.documents_manager = cls.env[
            "res.users"
        ].create(
            [
                {
                    "name": name,
                    "login": f"asset_compliance_{name.lower().replace(' ', '_')}",
                    "group_ids": [Command.set(cls.env.ref(group).ids)],
                }
                for name, group in (
                    ("Plain User", "base.group_user"),
                    ("IT Asset User", "asset_ledger.group_enable_it_assets"),
                    ("Documents Manager", "document.group_documents_manager"),
                )
            ]
        )
        cls.env["document.type"].create(
            {
                "name": "Access Asset Paper",
                "code": "ACCESS_ASSET_PAPER",
                "company_id": False,
                "is_mandatory": True,
                "applies_to": "resource.resource",
            }
        )
        cls.env.flush_all()
        cls.env["asset.compliance.report"].refresh()

    def _assets(self, user):
        return (
            self.env["asset.compliance.report"]
            .with_user(user)
            .search([("asset_id", "in", (self.vehicle | self.computer).ids)])
            .mapped("asset_id")
            .sudo()
        )

    def test_a_plain_internal_user_cannot_read_the_report(self):
        report = self.env["asset.compliance.report"].with_user(self.plain_user)

        with self.assertRaises(AccessError):
            report.search_count([])
        with self.assertRaises(AccessError):
            report.get_asset_compliance_by_kind()

    def test_an_asset_user_reads_only_the_kinds_they_are_enabled_for(self):
        self.assertEqual(self._assets(self.it_asset_user), self.computer)

    def test_a_documents_manager_reads_every_asset(self):
        self.assertEqual(
            self._assets(self.documents_manager), self.vehicle | self.computer
        )
