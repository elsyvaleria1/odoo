import logging
from collections import Counter
from contextlib import contextmanager
from unittest.mock import patch

from odoo import Command
from odoo.tests import TransactionCase
from odoo.tools.translate import code_translations

_logger = logging.getLogger(__name__)


class TestCopyTranslationsBatch(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("fr_FR")

    @contextmanager
    def _column_reads(self, sources):
        # the copies' own values are read back by update_field_translations,
        # one per copy: only the reads of what is copied from are counted
        reads = Counter()
        store = type(self.env.backend.columns)
        original = store.read
        source_ids = {(record._name, record.id) for record in sources}

        def spy(store_self, model, column, ids):
            if any((model._name, id_) in source_ids for id_ in ids):
                reads[model._name, column] += 1
            return original(store_self, model, column, ids)

        with patch.object(store, "read", spy):
            yield reads

    def _translated_records(self, count):
        records = self.env["test_orm.related_translation_1"].create(
            [
                {
                    "name": f"orm name {i}",
                    "html": f"<p>orm hello {i}</p><p>orm world</p>",
                }
                for i in range(count)
            ]
        )
        for i, record in enumerate(records):
            record.update_field_translations("name", {"fr_FR": f"orm nom {i}"})
            record.update_field_translations(
                "html",
                {
                    "fr_FR": {
                        f"orm hello {i}": f"orm bonjour {i}",
                        "orm world": "orm monde",
                    }
                },
            )
        self.env.flush_all()
        return records

    def _stored(self, records, name):
        records.flush_recordset([name])
        return records._fields[name]._get_stored_translations_multi(records)

    def test_fifty_copies_read_each_translated_field_once(self):
        records = self._translated_records(50)
        self.env.invalidate_all()
        before = self.cr.sql_statement_count
        with self._column_reads(records) as reads:
            copies = records.copy()
        queries = self.cr.sql_statement_count - before
        _logger.info(
            "copy of 50 records, 2 translated fields: %d queries, stored reads %s",
            queries,
            dict(reads),
        )
        self.assertEqual(reads["test_orm.related_translation_1", "name"], 1)
        self.assertEqual(reads["test_orm.related_translation_1", "html"], 1)

        fr = copies.with_context(lang="fr_FR")
        self.assertEqual(fr.mapped("name"), [f"orm nom {i}" for i in range(50)])
        self.assertEqual(
            fr.mapped("html"),
            [f"<p>orm bonjour {i}</p><p>orm monde</p>" for i in range(50)],
        )
        self.assertEqual(copies.mapped("name"), records.mapped("name"))
        self.assertEqual(copies.mapped("html"), records.mapped("html"))

    def test_a_batch_copy_stores_what_one_by_one_copies_store(self):
        records = self._translated_records(6)
        one_by_one = self.env["test_orm.related_translation_1"].concat(
            *(record.copy() for record in records)
        )
        batch = records.copy()
        for name in ("name", "html"):
            singles = self._stored(one_by_one, name)
            batched = self._stored(batch, name)
            sources = self._stored(records, name)
            for source, single, batched_copy in zip(
                records, one_by_one, batch, strict=True
            ):
                self.assertEqual(batched[batched_copy.id], singles[single.id])
                self.assertEqual(
                    batched[batched_copy.id]["fr_FR"], sources[source.id]["fr_FR"]
                )

    def test_archived_lines_of_a_batch_are_read_once(self):
        admin = self.env.user
        discussions = self.env["test_orm.discussion"].create(
            [
                {
                    "name": f"orm {i}",
                    "participants": [Command.set(admin.ids)],
                    "messages": [
                        Command.create({"label": f"active {i}"}),
                        Command.create({"label": f"archived {i}"}),
                    ],
                }
                for i in range(5)
            ]
        )
        for i, discussion in enumerate(discussions):
            active, archived = discussion.messages.sorted("id")
            active.update_field_translations("label", {"fr_FR": f"actif {i}"})
            archived.update_field_translations("label", {"fr_FR": f"archive {i}"})
            archived.active = False
        self.env.flush_all()
        self.env.invalidate_all()

        source_lines = discussions.with_context(active_test=False).messages
        with self._column_reads(source_lines) as reads:
            copies = discussions.copy()
        self.assertEqual(reads["test_orm.message", "label"], 1)
        for i, copy in enumerate(copies):
            lines = copy.with_context(active_test=False).messages.sorted("id")
            self.assertEqual(lines.mapped("active"), [True, False])
            self.assertEqual(
                lines.with_context(lang="fr_FR").mapped("label"),
                [f"actif {i}", f"archive {i}"],
            )
            self.assertEqual(lines.mapped("label"), [f"active {i}", f"archived {i}"])

    def test_an_excluded_field_is_neither_read_nor_copied(self):
        records = self._translated_records(3)
        with self._column_reads(records) as reads:
            copies = records.copy({"name": "orm given"})
        self.assertEqual(reads["test_orm.related_translation_1", "name"], 0)
        self.assertEqual(reads["test_orm.related_translation_1", "html"], 1)
        fr = copies.with_context(lang="fr_FR")
        self.assertEqual(fr.mapped("name"), ["orm given"] * 3)
        self.assertEqual(
            fr.mapped("html"),
            [f"<p>orm bonjour {i}</p><p>orm monde</p>" for i in range(3)],
        )

    def test_a_renamed_field_reads_the_batch_once(self):
        groups = self.env["res.groups"].create(
            [{"name": f"orm group {i}"} for i in range(4)]
        )
        for i, group in enumerate(groups):
            group.update_field_translations("name", {"fr_FR": f"orm groupe {i}"})
        self.env.flush_all()
        self.env.invalidate_all()
        with self._column_reads(groups) as reads:
            copies = groups.copy()
        self.assertEqual(reads["res.groups", "name"], 1)
        rename = code_translations.get_python_translations("base", "fr_FR").get(
            "%s (copy)", "%s (copy)"
        )
        self.assertEqual(
            copies.with_context(lang="fr_FR").mapped("name"),
            [rename % f"orm groupe {i}" for i in range(4)],
        )

    def test_a_translation_written_before_the_copy_is_flushed_first(self):
        records = self._translated_records(3)
        records[1].with_context(lang="fr_FR").name = "orm nom pending"
        copies = records.copy()
        self.assertEqual(
            copies.with_context(lang="fr_FR").mapped("name"),
            ["orm nom 0", "orm nom pending", "orm nom 2"],
        )

    def test_a_copy_made_in_another_language_keeps_both(self):
        records = self._translated_records(3)
        copies = records.with_context(lang="fr_FR").copy()
        english = copies.with_context(lang="en_US")
        self.assertEqual(english.mapped("name"), [f"orm name {i}" for i in range(3)])
        self.assertEqual(copies.mapped("name"), [f"orm nom {i}" for i in range(3)])
        self.assertEqual(
            english.mapped("html"),
            [f"<p>orm hello {i}</p><p>orm world</p>" for i in range(3)],
        )
        self.assertEqual(
            copies.mapped("html"),
            [f"<p>orm bonjour {i}</p><p>orm monde</p>" for i in range(3)],
        )
