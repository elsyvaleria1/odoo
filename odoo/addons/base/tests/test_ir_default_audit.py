from odoo.libs.json import loads as json_loads
from odoo.tests.common import TransactionCase, mute_logger, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestIrDefaultCompanyDependent(TransactionCase):
    def setUp(self):
        super().setUp()
        self.IrDefault = self.env["ir.default"]
        self.IrDefault.search([("field_id.model", "=", "res.partner")]).unlink()
        self.assertTrue(self.env["res.partner"]._fields["barcode"].company_dependent)

    def _existing_company_ids(self):
        self.env.flush_all()
        self.env.cr.execute("SELECT ARRAY_AGG(id) FROM res_company")
        company_ids = self.env.cr.fetchone()[0] or []
        self.env.invalidate_all()
        return set(company_ids)

    def test_field_column_fallbacks_no_default(self):
        result = json_loads(
            self.IrDefault._get_field_column_fallbacks("res.partner", "barcode")
        )
        company_ids = self._existing_company_ids()
        self.assertEqual({int(cid) for cid in result}, company_ids)
        self.assertTrue(all(value is None for value in result.values()))

    def test_field_column_fallbacks_with_default(self):
        self.IrDefault.set(
            "res.partner", "barcode", "DEFBC", user_id=False, company_id=False
        )
        result = json_loads(
            self.IrDefault._get_field_column_fallbacks("res.partner", "barcode")
        )
        company_ids = self._existing_company_ids()
        self.assertEqual({int(cid) for cid in result}, company_ids)
        self.assertTrue(all(value == "DEFBC" for value in result.values()))

    def test_field_column_fallbacks_company_added(self):
        first = json_loads(
            self.IrDefault._get_field_column_fallbacks("res.partner", "barcode")
        )
        new_company = self.env["res.company"].create({"name": "Audit Co"})
        second = json_loads(
            self.IrDefault._get_field_column_fallbacks("res.partner", "barcode")
        )
        self.assertNotIn(str(new_company.id), first)
        self.assertIn(str(new_company.id), second)
        self.assertEqual(set(first) | {str(new_company.id)}, set(second))

    @mute_logger("odoo.fields")
    def test_evaluate_condition_true_and_false(self):
        self.assertIs(
            self.env.registry.metaschema.evaluate_default_condition(
                self.env, "res.partner", "barcode", "=", False
            ),
            True,
        )
        self.assertIs(
            self.env.registry.metaschema.evaluate_default_condition(
                self.env, "res.partner", "barcode", "!=", False
            ),
            False,
        )

    @mute_logger("odoo.fields")
    def test_evaluate_condition_unknown_returns_none(self):
        new_test_user(self.env, login="ird_audit_user")
        self.assertIsNone(
            self.env.registry.metaschema.evaluate_default_condition(
                self.env, "res.partner", "barcode", "definitely_not_an_operator", "x"
            )
        )
