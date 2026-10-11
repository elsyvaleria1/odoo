from unittest.mock import patch

import odoo.tests
from odoo.orm.runtime._registry_capabilities import _TextTables
from odoo.tests import counting_statements

from odoo.addons.base.tests.test_expression import TransactionExpressionCase
from odoo.addons.base.tests.test_translate import SPECIAL_CHARACTERS


@odoo.tests.tagged("post_install", "-at_install")
class TestIndexedTranslation(TransactionExpressionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("fr_FR")

    def test_search_ilike(self):
        record_en = (
            self.env["test_orm.indexed_translation"]
            .with_context(lang="en_US")
            .create({})
        )
        record_fr = record_en.with_context(lang="fr_FR")
        record_en.name = '<div class="my_class">hello</div>\n<div/>'
        record_fr.name = '<div class="my_class">%bonjour\\</div>\a<div/>'

        self.assertEqual(record_en.name, '<div class="my_class">hello</div>\n<div/>')
        self.assertEqual(
            record_fr.name, '<div class="my_class">%bonjour\\</div>\a<div/>'
        )

        self.assertEqual(
            self._search(record_en, [("name", "ilike", 'class="my_class')]),
            record_en,
        )

        self.assertEqual(
            self._search(record_en, [("name", "ilike", r"class%class")]),
            record_en,
        )
        self.assertEqual(
            self._search(record_en, [("name", "ilike", r'class="m_\_class')]),
            record_en,
        )
        self.assertEqual(
            self._search(record_en, [("name", "ilike", "bonjour")]),
            record_en.browse(),
        )
        self.assertEqual(
            self._search(record_en, [("name", "ilike", "</div>\n<div/>")]),
            record_en,
        )
        self.assertEqual(
            self._search(record_fr, [("name", "ilike", "</div>\a<div/>")]),
            record_fr,
        )
        self.assertEqual(
            self._search(record_fr, [("name", "ilike", r"\%bonjour\\")]),
            record_fr,
        )

        self.assertEqual(
            self._search(
                record_en,
                [("name", "=", '<div class="my_class">hello</div>\n<div/>')],
            ),
            record_en,
        )
        self.assertEqual(
            self._search(
                record_fr,
                [
                    (
                        "name",
                        "=",
                        '<div class="my_class">%bonjour\\</div>\a<div/>',
                    )
                ],
            ),
            record_fr,
        )

        with self.assertQueries(
            [
                """
            SELECT "test_orm_indexed_translation"."id"
            FROM "test_orm_indexed_translation"
            WHERE (jsonb_path_query_array("test_orm_indexed_translation"."name", '$.*')::text ILIKE %s
            AND "test_orm_indexed_translation"."name"->>%s ILIKE %s)
            ORDER BY "test_orm_indexed_translation"."id"
        """,
                """
            SELECT "test_orm_indexed_translation"."id"
            FROM "test_orm_indexed_translation"
            WHERE (jsonb_path_query_array("test_orm_indexed_translation"."name", '$.*')::text ILIKE %s
            AND COALESCE("test_orm_indexed_translation"."name"->>%s, "test_orm_indexed_translation"."name"->>%s) ILIKE %s)
            ORDER BY "test_orm_indexed_translation"."id"
        """,
                """
            SELECT "test_orm_indexed_translation"."id"
            FROM "test_orm_indexed_translation"
            ORDER BY "test_orm_indexed_translation"."id"
        """,
            ]
        ):
            record_en.search([("name", "ilike", "foo")])
            record_fr.search([("name", "ilike", "foo")])
            record_fr.search([("name", "ilike", "")])
            record_fr.search([("name", "not ilike", "")])

    def test_search_special_characters(self):
        name_en = f"{SPECIAL_CHARACTERS}_en"
        name_fr = f"{SPECIAL_CHARACTERS}_fr"
        record_en = (
            self.env["test_orm.indexed_translation"]
            .with_context(lang="en_US")
            .create({})
        )
        record_fr = record_en.with_context(lang="fr_FR")
        record_en.name = name_en
        record_fr.name = name_fr

        self.assertEqual(
            self._search(record_en, [("name", "ilike", name_en)]), record_en
        )
        self.assertEqual(self._search(record_en, [("name", "=", name_en)]), record_en)
        self.assertEqual(
            self._search(record_en, [("name", "in", [name_en])]), record_en
        )

        self.assertEqual(
            self._search(record_fr, [("name", "ilike", name_fr)]), record_en
        )
        self.assertEqual(self._search(record_fr, [("name", "=", name_fr)]), record_en)
        self.assertEqual(
            self._search(record_fr, [("name", "in", [name_fr])]), record_en
        )

        self.assertFalse(self._search(record_fr, [("name", "ilike", name_en)]))
        self.assertFalse(self._search(record_fr, [("name", "=", name_en)]))
        self.assertFalse(self._search(record_fr, [("name", "in", [name_en])]))

        self.assertFalse(self._search(record_en, [("name", "ilike", name_fr)]))
        self.assertFalse(self._search(record_en, [("name", "=", name_fr)]))
        self.assertFalse(self._search(record_en, [("name", "in", [name_fr])]))

    def test_search_quotes_and_backslashes(self):
        Model = self.env["test_orm.indexed_translation"].with_context(lang="en_US")
        tubo, x_galv, a_b, codo, ab_cd = Model.create(
            [
                {"name": "Tubo 1/2″"},
                {"name": 'x"Galv'},
                {"name": "a\\b"},
                {"name": "Codo “Galvanizado”"},
                {"name": "ab＼cd"},
            ]
        )
        records = tubo | x_galv | a_b | codo | ab_cd
        cases = [
            ("ilike", 'x"Galv', x_galv),
            ("like", 'x"Galv', x_galv),
            ("=like", 'x"Ga%', x_galv),
            ("ilike", "“Galvanizado”", codo),
            ("like", "Codo “Galv", codo),
            ("like", "1/2″", tubo),
            ("ilike", "a\\\\b", a_b),
            ("like", "a\\\\b", a_b),
            ("like", "ab＼cd", ab_cd),
            ("=like", "ab＼c_", ab_cd),
            ("in", ["ab＼cd"], ab_cd),
            ("in", ["Tubo 1/2″"], tubo),
            ("in", ['x"Galv'], x_galv),
            ("in", ["Codo “Galvanizado”"], codo),
        ]
        if self.env.registry.unaccent_status:
            cases += [
                ("ilike", '1/2"', tubo),
                ("=ilike", 'tubo 1/2"', tubo),
                ("ilike", '"Galvanizado"', codo),
                ("ilike", "“Galvanizado″", codo),
                ("ilike", "x“Galv", x_galv),
                ("ilike", "x＂galv", x_galv),
                ("ilike", "ab\\\\cd", ab_cd),
                ("=ilike", "AB\\\\C%", ab_cd),
            ]
        for operator, value, expected in cases:
            with self.subTest(operator=operator, value=value):
                found = self._search(Model, [("name", operator, value)])
                self.assertEqual(found & records, expected)

    def test_search_many_quotes_keeps_the_prefilter(self):
        Model = self.env["test_orm.indexed_translation"].with_context(lang="en_US")
        plain, primed, spaced = Model.create(
            [
                {"name": 'Tubo 1"x2"x3"'},
                {"name": "Tubo 1″x2″x3″"},
                {"name": 'Tubo "x" "y" "z"'},
            ]
        )
        records = plain | primed | spaced
        unaccented = bool(self.env.registry.unaccent_status)
        cases = [
            ("ilike", '1"x2"x3"', plain | primed if unaccented else plain),
            ("=ilike", 'tubo 1"X2"x3"', plain | primed if unaccented else plain),
            ("like", '1"x2"x3"', plain),
            ("ilike", 'Tubo "x" "y" "z"', spaced),
            ("ilike", '"x" "y" "z', spaced),
        ]
        for operator, value, expected in cases:
            with self.subTest(operator=operator, value=value):
                domain = [("name", operator, value)]
                where = Model._search(domain).where_clause
                self.assertIn("jsonb_path_query_array", where.code)
                self.assertEqual(self._search(Model, domain) & records, expected)

    def _count_search_statements(self, Model, value):
        self.env.flush_all()
        with counting_statements(self.cr) as statements:
            Model.search([("name", "ilike", value)])
            return statements.count

    def test_first_ascii_search_reads_no_character_table(self):
        Model = self.env["test_orm.indexed_translation"].with_context(lang="en_US")
        with (
            patch.dict(_TextTables.by_db, clear=True),
            patch.object(self.env.registry, "_text_transforms", None),
        ):
            cold = self._count_search_statements(Model, "abc")
            warm = self._count_search_statements(Model, "abd")
            self.assertEqual(cold, warm)
            self.assertFalse(_TextTables.by_db)

    def test_the_character_cache_gives_way_to_the_bounded_table(self):
        from odoo.orm.runtime import _registry_capabilities

        Model = self.env["test_orm.indexed_translation"].with_context(lang="en_US")
        db = self.env.registry.db_name
        with (
            patch.dict(_TextTables.by_db, clear=True),
            patch.dict(_TextTables.unaccented_chars, clear=True),
            patch.object(self.env.registry, "_text_transforms", None),
            patch.object(_registry_capabilities, "_UNACCENT_COVERING_MAX", 10),
        ):
            Model.search([("name", "ilike", "".join(map(chr, range(0x4E00, 0x4E20))))])
            self.assertNotIn(db, _TextTables.unaccented_chars)
            self.assertIn(db, _TextTables.by_db)

    def test_first_non_ascii_search_reads_only_its_characters(self):
        Model = self.env["test_orm.indexed_translation"].with_context(lang="en_US")
        with (
            patch.dict(_TextTables.by_db, clear=True),
            patch.dict(_TextTables.unaccented_chars, clear=True),
            patch.object(self.env.registry, "_text_transforms", None),
        ):
            cold = self._count_search_statements(Model, "Café")
            warm = self._count_search_statements(Model, "Cafés")
            self.assertEqual(warm, self._count_search_statements(Model, "abc"))
            self.assertLessEqual(cold, warm + 1)
            self.assertFalse(_TextTables.by_db)
