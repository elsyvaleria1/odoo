from unittest.mock import patch

from odoo import Command
from odoo.fields import Domain
from odoo.libs.sql import SQL
from odoo.orm.models.field_classes import FieldAccessClasses
from odoo.tests import TransactionCase, new_test_user
from odoo.tools import mute_logger

from odoo.addons.base.tests.common import TransactionCaseWithUserDemo, make_guard_row


class TestLoadBatches(TransactionCase):
    def test_a_batch_rolled_back_at_release_keeps_none_of_its_ids(self):
        Cat = self.env["test_orm.category"]
        original = type(Cat)._load_records

        def poisoned(self, data_list, update=False):
            records = original(self, data_list, update)
            if len(data_list) > 1:
                records[0].color = -1
            return records

        with (
            patch.object(type(Cat), "_load_records", poisoned),
            mute_logger("odoo.db.cursor", "odoo.db.savepoint", "odoo.models"),
        ):
            result = Cat.load(["name", "color"], [["orm one", "1"], ["orm two", "2"]])
        self.assertEqual(result["messages"], [])
        self.assertEqual(len(result["ids"]), 2)
        cats = Cat.browse(result["ids"])
        self.assertEqual(cats.exists(), cats)
        self.assertEqual(cats.mapped("name"), ["orm one", "orm two"])

    def test_a_repeated_external_id_creates_one_record(self):
        Discussion = self.env["test_orm.discussion"]
        result = Discussion.load(
            ["id", "name"], [["orm_dup", "orm first"], ["orm_dup", "orm second"]]
        )
        self.assertEqual(result["messages"], [])
        record = self.env.ref("__import__.orm_dup")
        self.assertEqual(result["ids"], [record.id, record.id])
        self.assertEqual(
            Discussion.search([("name", "in", ["orm first", "orm second"])]), record
        )
        self.assertEqual(record.name, "orm second")


class TestCopyTranslations(TransactionCase):
    def test_archived_lines_keep_their_translations(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        admin = self.env.user
        discussion = self.env["test_orm.discussion"].create(
            {
                "name": "orm",
                "participants": [Command.set(admin.ids)],
                "messages": [
                    Command.create({"label": "active"}),
                    Command.create({"label": "archived"}),
                ],
            }
        )
        active, archived = discussion.messages.sorted("id")
        active.update_field_translations("label", {"fr_FR": "actif"})
        archived.update_field_translations("label", {"fr_FR": "archive"})
        archived.active = False

        copy = discussion.copy()
        lines = copy.with_context(active_test=False).messages.sorted("id")
        self.assertEqual(lines.mapped("active"), [True, False])
        self.assertEqual(
            lines.with_context(lang="fr_FR").mapped("label"), ["actif", "archive"]
        )
        self.assertEqual(lines.mapped("label"), ["active", "archived"])

    def test_nothing_to_copy_writes_nothing(self):
        Model = self.env["test_orm.related_translation_1"]
        record = Model.create({"name": "orm", "html": "<p>orm</p>"})
        calls = []
        original = type(Model).update_field_translations

        def spy(self, field_name, translations, source_lang=""):
            calls.append((field_name, dict(translations)))
            return original(self, field_name, translations, source_lang)

        with patch.object(type(Model), "update_field_translations", spy):
            copy = record.copy()
            self.assertEqual(calls, [])
            self.env["res.lang"]._activate_lang("fr_FR")
            record.copy()
            self.assertEqual(calls, [])
            record.update_field_translations("name", {"fr_FR": "orm fr"})
            calls.clear()
            translated = record.copy()
            self.assertEqual(calls, [("name", {"fr_FR": "orm fr"})])
        self.assertEqual((copy.name, copy.html), ("orm", "<p>orm</p>"))
        self.assertEqual(translated.with_context(lang="fr_FR").name, "orm fr")


class TestFieldAccessMaskWithoutQuery(TransactionCase):
    def test_a_joining_mask_runs_inside_a_plain_where(self):
        user = new_test_user(self.env, "orm_mask", groups="base.group_user")
        Message = self.env["test_orm.message"]
        shown, hidden = self.env["test_orm.discussion"].create(
            [
                {"name": "orm shown", "participants": [Command.set(self.env.user.ids)]},
                {
                    "name": "orm hidden",
                    "participants": [Command.set(self.env.user.ids)],
                },
            ]
        )
        seen, unseen = Message.create(
            [{"discussion": shown.id}, {"discussion": hidden.id}]
        )
        field = Message._fields["body"]
        domain = Domain("discussion", "any!", Domain("name", "=", "orm shown"))
        with (
            patch.object(
                field, "access_classes", FieldAccessClasses(read=("orm",), write=())
            ),
            patch.object(
                type(Message),
                "_field_access_domain",
                lambda self, field, operation: domain,
            ),
        ):
            mask = Message.with_user(user)._field_access_mask_sql(
                field, Message._table, None
            )
        Message.flush_model()
        rows = self.env.execute_query(
            SQL(
                "SELECT id FROM %s WHERE id IN %s AND %s",
                SQL.identifier(Message._table),
                tuple((seen + unseen).ids),
                mask,
            )
        )
        self.assertEqual([id_ for (id_,) in rows], seen.ids)


class TestDescendantIds(TransactionCaseWithUserDemo):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Cat = cls.env["test_orm.category"]
        cls.top = Cat.create({"name": "orm top"})
        cls.middle = Cat.create({"name": "orm middle", "parent": cls.top.id})
        cls.bottom = Cat.create({"name": "orm bottom", "parent": cls.middle.id})

    def test_a_rule_hiding_nodes_does_not_cut_the_tree(self):
        make_guard_row(
            self.env,
            "test_orm.category",
            str([("id", "=", self.bottom.id)]),
            "base.group_user",
        )
        top = self.top.with_user(self.user_demo)
        self.assertEqual(
            set(top._get_descendant_ids(include_self=True)),
            {self.top.id, self.middle.id, self.bottom.id},
        )
        self.assertEqual(
            set(top._get_descendant_ids()), {self.middle.id, self.bottom.id}
        )
        self.assertEqual(
            list(self.bottom.with_user(self.user_demo)._get_ancestor_ids()),
            [self.top.id, self.middle.id],
        )


class TestBinarySizeAfterWrite(TransactionCase):
    def test_a_size_read_sees_the_content_written_before_it(self):
        foo = self.env["test_orm.related_foo"].create(
            {"name": "f", "binary_bin": b"QUJD"}
        )
        foo.flush_recordset()
        foo.binary_bin = b"QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo="
        size = foo.with_context(bin_size=True).binary_bin
        self.assertEqual(size, "36 bytes")
