from markupsafe import Markup

from odoo import Command
from odoo.tests.common import TransactionCase


class TestCreateInverseFlush(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tags = cls.env["test_orm.category"].create([{"name": "a"}, {"name": "b"}])

    def _create(self, **vals):
        return self.env["test_orm.delegating"].create(
            {
                "name": "Roger",
                "note": Markup("<p>hi</p>"),
                "tag_ids": [Command.set(self.tags.ids)],
                **vals,
            }
        )

    def test_a_flush_in_an_inverse_computes_from_the_inherited_values(self):
        record = self._create(preference="x")
        self.assertEqual(record.signature, "-- Roger")
        self.assertEqual(record.note_text, "<p>hi</p>")
        self.assertEqual(record.tag_count, 2)

    def test_the_inherited_values_read_back_after_an_inverse_flushed(self):
        record = self._create(preference="x")
        self.assertEqual(record.name, "Roger")
        self.assertEqual(record.note, Markup("<p>hi</p>"))
        self.assertEqual(record.tag_ids, self.tags)

    def test_an_inverse_flush_computes_what_a_plain_create_computes(self):
        flushed = self._create(preference="x")
        plain = self._create()
        for fname in ("signature", "note_text", "tag_count"):
            self.assertEqual(flushed[fname], plain[fname], fname)
