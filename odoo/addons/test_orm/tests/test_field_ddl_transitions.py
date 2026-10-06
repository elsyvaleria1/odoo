from datetime import datetime
from unittest.mock import patch

from odoo.db import schema as sql
from odoo.libs.sql import SQL
from odoo.orm.fields import _field_ddl
from odoo.tests import common


def _column(env, table, name):
    return sql.get_table_columns(env.cr, table)[name]


class TestCompanyDependentColumnTransitions(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.main_company = cls.env.ref("base.main_company")
        cls.other_company = cls.env["res.company"].create({"name": "R2 Second"})
        cls.partner = cls.env["res.partner"].create({"name": "R2 Partner"})
        cls.env["ir.model"].create(
            {
                "name": "R2 Company Dependent Probe",
                "model": "x_cd_probe",
                "field_id": [
                    (0, 0, {"name": "x_name", "ttype": "char"}),
                    (0, 0, {"name": "x_label", "ttype": "char"}),
                    (0, 0, {"name": "x_qty", "ttype": "integer"}),
                    (0, 0, {"name": "x_ratio", "ttype": "float"}),
                    (0, 0, {"name": "x_flag", "ttype": "boolean"}),
                    (0, 0, {"name": "x_when", "ttype": "datetime"}),
                    (
                        0,
                        0,
                        {
                            "name": "x_partner_id",
                            "ttype": "many2one",
                            "relation": "res.partner",
                        },
                    ),
                    (0, 0, {"name": "x_code", "ttype": "char", "size": 2}),
                ],
            }
        )

    def _field(self, name):
        return self.env["ir.model.fields"]._get("x_cd_probe", name)

    def _model(self, company):
        return self.env["x_cd_probe"].with_company(company)

    def _raw(self, record, name):
        self.env.flush_all()
        return self.env.execute_query(
            SQL(
                "SELECT %s FROM x_cd_probe WHERE id = %s",
                SQL.identifier(name),
                record.id,
            )
        )[0][0]

    def test_a_plain_value_becomes_every_company_value(self):
        when = datetime(2026, 10, 3, 8, 30, 15)
        model = self._model(self.main_company)
        filled = model.create(
            {
                "x_qty": 7,
                "x_ratio": 0.25,
                "x_flag": True,
                "x_when": when,
                "x_partner_id": self.partner.id,
                "x_label": "plain",
            }
        )
        empty = model.create({})
        self.env.flush_all()

        for name in ("x_qty", "x_ratio", "x_flag", "x_when", "x_partner_id", "x_label"):
            self._field(name).company_dependent = True

        self.assertEqual(_column(self.env, "x_cd_probe", "x_qty")["udt_name"], "jsonb")
        for company in (self.main_company, self.other_company):
            record = self.env["x_cd_probe"].browse(filled.id).with_company(company)
            self.assertEqual(record.x_qty, 7)
            self.assertEqual(record.x_ratio, 0.25)
            self.assertTrue(record.x_flag)
            self.assertEqual(record.x_when, when)
            self.assertEqual(record.x_partner_id, self.partner)
            self.assertEqual(record.x_label, "plain")
        company_ids = (
            self.env["res.company"].with_context(active_test=False).search([]).ids
        )
        self.assertEqual(
            self._raw(filled, "x_qty"), {str(id_): 7 for id_ in company_ids}
        )
        self.assertEqual(
            self._raw(filled, "x_when"),
            {str(id_): "2026-10-03 08:30:15" for id_ in company_ids},
        )
        self.assertIsNone(self._raw(empty, "x_qty"))
        self.assertIsNone(self._raw(empty, "x_label"))
        self.assertFalse(
            sql._get_fk_constraints(self.env.cr, "x_cd_probe", "x_partner_id")
        )
        self.assertEqual(
            self.env["x_cd_probe"].search([("x_qty", "=", 7)]).ids, filled.ids
        )

    def test_a_company_value_becomes_the_main_company_value(self):
        self._field("x_name").company_dependent = True
        self._field("x_qty").company_dependent = True
        main = self._model(self.main_company).create({"x_name": "main", "x_qty": 3})
        main.with_company(self.other_company).write({"x_name": "other", "x_qty": 9})
        only_other = self._model(self.other_company).create(
            {"x_name": "elsewhere", "x_qty": 4}
        )
        self.env.flush_all()

        self._field("x_name").company_dependent = False
        self._field("x_qty").company_dependent = False

        column = _column(self.env, "x_cd_probe", "x_name")
        self.assertEqual(column["udt_name"], "varchar")
        self.assertEqual(self._raw(main, "x_name"), "main")
        self.assertEqual(self._raw(main, "x_qty"), 3)
        self.assertIsNone(self._raw(only_other, "x_name"))
        self.assertIsNone(self._raw(only_other, "x_qty"))

    def test_a_company_value_falls_back_on_the_main_company_default(self):
        self._field("x_qty").company_dependent = True
        record = self._model(self.other_company).create({"x_qty": 4})
        self.env["ir.default"].set(
            "x_cd_probe", "x_qty", 11, company_id=self.main_company.id
        )
        self.env.flush_all()
        self.assertEqual(record.with_company(self.main_company).x_qty, 11)

        self._field("x_qty").company_dependent = False

        self.assertEqual(self._raw(record, "x_qty"), 11)

    def test_a_translated_value_keeps_its_english_text_when_leaving_translation(self):
        self._field("x_name").translate = "standard"
        record = self._model(self.main_company).create({"x_name": "hello"})
        self.env.flush_all()
        self.assertEqual(self._raw(record, "x_name"), {"en_US": "hello"})

        self._field("x_name").translate = False

        self.assertEqual(self._raw(record, "x_name"), "hello")

    def test_a_sized_char_compares_without_cutting_the_comparand(self):
        record = self._model(self.main_company).create({"x_code": "ME"})
        self.env.flush_all()
        model = self.env["x_cd_probe"]
        self.assertFalse(model.search([("x_code", "=", "MEX")]))
        self.assertFalse(model.search([("x_code", "in", ["MEX", "FRA"])]))
        self.assertEqual(model.search([("x_code", "=", "ME")]), record)
        self.assertFalse(
            model.search([("x_code", ">=", "MEX"), ("id", "=", record.id)])
        )
        self.assertEqual(
            model.search([("x_code", "<", "MEX"), ("id", "=", record.id)]), record
        )


class TestSqlDefaultReconciliation(common.TransactionCase):
    def setUp(self):
        super().setUp()
        self.model = self.env["test_orm.mixed"]
        self.table = self.model._table
        self.field = self.model._fields["foo"]

    def _default(self, name="foo"):
        return sql.get_column_default(self.env.cr, self.table, name)

    def _update(self, **attrs):
        column = _column(self.env, self.table, self.field.name)
        with patch.multiple(self.field, **attrs):
            _field_ddl.update_db_notnull(self.field, self.model, column)

    def _set_not_null(self, name, value):
        self.model.create({name: value})
        self.env.flush_all()
        self.env.cr.execute(
            SQL(
                "UPDATE %s SET %s = %s WHERE %s IS NULL",
                SQL.identifier(self.table),
                SQL.identifier(name),
                value,
                SQL.identifier(name),
            )
        )
        sql.set_not_null(self.env.cr, self.table, name)

    def test_a_required_literal_default_follows_the_declaration(self):
        self._set_not_null("foo", "x")

        self._update(required=True, default_literal="first")
        self.assertTrue(_field_ddl.is_sql_default_equal(self._default(), "first"))

        self.env.cr.execute(
            SQL("INSERT INTO %s DEFAULT VALUES", SQL.identifier(self.table))
        )

        self._update(required=True, default_literal="second")
        self.assertTrue(_field_ddl.is_sql_default_equal(self._default(), "second"))

        self._update(required=True, default_literal=None)
        self.assertIsNone(self._default())

    def test_an_optional_field_loses_the_default_it_had_while_required(self):
        self._set_not_null("foo", "x")
        self._update(required=True, default_literal="kept")
        self.assertIsNotNone(self._default())

        self._update(required=False, default_literal="kept")

        self.assertEqual(_column(self.env, self.table, "foo")["is_nullable"], "YES")
        self.assertIsNone(self._default())

    def test_a_boolean_default_follows_the_declaration_too(self):
        self.field = self.model._fields["truth"]
        self._set_not_null("truth", False)
        self._update(required=True, default_literal=True)
        self.assertTrue(_field_ddl.is_sql_default_equal(self._default("truth"), True))

        self._update(required=False, default_literal=True)
        self.assertIsNone(self._default("truth"))

        sql.set_default(self.env.cr, self.table, "truth", False)
        self._set_not_null("truth", False)
        self._update(required=True, default_literal=None)
        self.assertIsNone(self._default("truth"))
