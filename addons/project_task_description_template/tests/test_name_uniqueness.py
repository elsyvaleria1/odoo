import psycopg

from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


class TestTemplateNameUniqueness(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Template = cls.env["project.task.description.template"]
        cls.company = cls.env.company

    def _create(self, name, **kw):
        return self.Template.create(
            dict({"name": name, "description": "<p>Body</p>"}, **kw)
        )

    @mute_logger("odoo.sql_db")
    def test_duplicate_name_in_one_company_is_refused(self):
        self._create("Uniq Sprint")
        self.env.flush_all()
        with self.assertRaises(psycopg.errors.UniqueViolation):
            with self.cr.savepoint():
                self._create("Uniq Sprint")
                self.env.flush_all()

    def test_same_name_in_another_company_is_allowed(self):
        other = self.env["res.company"].create({"name": "Uniq Other Co"})
        self._create("Uniq Shared")
        self._create("Uniq Shared", company_id=other.id)
        self.env.flush_all()
        self.assertEqual(
            self.Template.search_count([("name", "=", "Uniq Shared")]),
            2,
            "the unique index is per company, so both records must survive",
        )

    @mute_logger("odoo.sql_db")
    def test_a_translated_duplicate_is_still_refused(self):
        self.env["res.lang"]._activate_lang("es_MX")
        self._create("Uniq Translated")
        self.env.flush_all()
        with self.assertRaises(psycopg.errors.UniqueViolation):
            with self.cr.savepoint():
                self.Template.with_context(lang="es_MX").create(
                    {"name": "Uniq Translated", "description": "<p>Body</p>"}
                )
                self.env.flush_all()

    @mute_logger("odoo.sql_db")
    def test_a_null_company_still_collides(self):
        self._create("Uniq Global", company_id=False)
        self.env.flush_all()
        with self.assertRaises(psycopg.errors.UniqueViolation):
            with self.cr.savepoint():
                self._create("Uniq Global", company_id=False)
                self.env.flush_all()
