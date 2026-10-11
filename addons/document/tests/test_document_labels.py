from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import new_test_user
from odoo.tests.common import tagged

from .test_document_common import TransactionCaseDocuments


@tagged("post_install", "-at_install")
class TestDocumentLabels(TransactionCaseDocuments):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.confidential = cls.env["ir.access.class"].create(
            {"name": "document.test_confidential"}
        )
        readers = cls.env["res.groups"].create({"name": "Confidential readers"})
        writers = cls.env["res.groups"].create({"name": "Confidential writers"})
        cls.env["ir.access"].create(
            [
                {
                    "name": "confidential: readers read",
                    "class_id": cls.confidential.id,
                    "group_id": readers.id,
                    "kind": "permission",
                    "operation": "r",
                },
                {
                    "name": "confidential: writers write",
                    "class_id": cls.confidential.id,
                    "group_id": writers.id,
                    "kind": "permission",
                    "operation": "ru",
                },
            ]
        )
        groups = "base.group_user,document.group_documents_user"
        cls.plain = new_test_user(cls.env, login="doc_lbl_plain", groups=groups)
        cls.reader = new_test_user(cls.env, login="doc_lbl_reader", groups=groups)
        cls.writer = new_test_user(cls.env, login="doc_lbl_writer", groups=groups)
        cls.reader.group_ids = [Command.link(readers.id)]
        cls.writer.group_ids = [Command.link(writers.id)]
        Document = cls.env["document.document"]
        cls.root = Document.create(
            {"name": "Labels", "type": "folder", "user_folder_id": "COMPANY"}
        )
        cls.root.action_update_access_rights(access_internal="edit")
        cls.folder = Document.create(
            {"name": "Board", "type": "folder", "folder_id": cls.root.id}
        )
        cls.minutes = Document.create(
            {"name": "Minutes", "type": "binary", "folder_id": cls.folder.id}
        )
        cls.folder.access_label_id = cls.confidential
        cls.documents = cls.root | cls.folder | cls.minutes

    def permissions(self, user):
        documents = self.documents.with_user(user).sudo()
        documents.invalidate_recordset(["user_permission", "user_can_manage"])
        return {
            doc.name: (doc.user_permission, doc.user_can_manage) for doc in documents
        }

    def visible(self, user):
        found = (
            self.env["document.document"]
            .with_user(user)
            .search([("id", "in", self.documents.ids)])
        )
        return set(found.mapped("name"))

    def test_a_folder_s_label_reaches_its_documents_live(self):
        self.assertEqual(self.minutes.access_inherited_label_id, self.confidential)
        self.assertEqual(self.visible(self.plain), {"Labels"})
        self.assertEqual(self.visible(self.reader), {"Labels", "Board", "Minutes"})
        self.assertEqual(self.permissions(self.plain)["Minutes"], ("none", False))
        self.assertEqual(self.permissions(self.reader)["Minutes"], ("view", False))
        self.assertEqual(self.permissions(self.writer)["Minutes"], ("edit", False))
        with self.assertRaises(AccessError):
            self.minutes.with_user(self.reader).write({"name": "Leaked"})
        self.minutes.with_user(self.writer).write({"name": "Minutes"})

        self.minutes.folder_id = self.root
        self.assertIn("Minutes", self.visible(self.plain))

    def test_only_who_manages_a_document_labels_it(self):
        archive = self.env["document.document"].create(
            {"name": "Archive", "type": "folder", "folder_id": self.root.id}
        )
        with self.assertRaises(AccessError):
            archive.with_user(self.plain).write(
                {"access_label_id": self.confidential.id}
            )
        self.env["document.access"].create(
            {
                "document_id": archive.id,
                "partner_id": self.writer.partner_id.id,
                "role": "manage",
            }
        )
        archive.with_user(self.writer).write({"access_label_id": self.confidential.id})
        self.assertNotIn(
            archive, self.env["document.document"].with_user(self.plain).search([])
        )

    def _class(self, name, *rows):
        access_class = self.env["ir.access.class"].create({"name": name})
        self.env["ir.access"].create(
            [
                {"name": f"{name}: {index}", "class_id": access_class.id, **row}
                for index, row in enumerate(rows)
            ]
        )
        return access_class

    def test_a_class_someone_writes_without_reading_cannot_label(self):
        everyone = self.env.ref("base.group_everyone")
        user = self.env.ref("base.group_user")
        write_only = self._class(
            "document.test_write_only",
            {"group_id": everyone.id, "kind": "permission", "operation": "u"},
        )
        blind_writers = self._class(
            "document.test_blind_writers",
            {"group_id": user.id, "kind": "permission", "operation": "r"},
            {"group_id": everyone.id, "kind": "permission", "operation": "u"},
        )
        read_guarded = self._class(
            "document.test_read_guarded",
            {"group_id": user.id, "kind": "permission", "operation": "ru"},
            {
                "group_id": user.id,
                "kind": "guard",
                "guard_scope": "members",
                "operation": "r",
                "reach": "none",
            },
        )
        write_guarded = self._class(
            "document.test_write_guarded",
            {"group_id": user.id, "kind": "permission", "operation": "ru"},
            {
                "group_id": user.id,
                "kind": "guard",
                "guard_scope": "members",
                "operation": "u",
                "reach": "none",
            },
        )
        refused = write_only | blind_writers | read_guarded
        candidates = refused | write_guarded | self.confidential
        self.assertEqual(
            candidates.filtered("can_label"), write_guarded | self.confidential
        )
        self.assertEqual(
            self.env["ir.access.class"].search(
                [("id", "in", candidates.ids), ("can_label", "=", True)]
            ),
            write_guarded | self.confidential,
        )
        self.assertEqual(
            self.env["ir.access.class"].search(
                [("id", "in", candidates.ids), ("can_label", "=", False)]
            ),
            refused,
        )
        for access_class in refused:
            with self.subTest(access_class.name), self.assertRaises(ValidationError):
                self.minutes.access_label_id = access_class
        with self.assertRaises(ValidationError):
            self.env["document.document"].create(
                {
                    "name": "Sealed",
                    "folder_id": self.root.id,
                    "access_label_id": write_only.id,
                }
            )
        self.minutes.access_label_id = write_guarded

    def test_a_label_s_class_cannot_come_to_let_writing_without_reading(self):
        writers = self.env["ir.access"].search(
            [("class_id", "=", self.confidential.id), ("operation", "=", "ru")]
        )
        with self.assertRaises(ValidationError):
            writers.operation = "u"
        with self.assertRaises(ValidationError):
            self.env["ir.access"].create(
                {
                    "name": "confidential: everyone writes",
                    "class_id": self.confidential.id,
                    "group_id": self.env.ref("base.group_everyone").id,
                    "kind": "permission",
                    "operation": "u",
                }
            )
        self.folder.access_label_id = False
        writers.operation = "u"
        self.assertFalse(self.confidential.can_label)

    def test_a_class_reader_s_reach_is_searched_once(self):
        self._class(
            "document.test_write_only",
            {
                "group_id": self.env.ref("base.group_everyone").id,
                "kind": "permission",
                "operation": "u",
            },
        )
        Document = self.env["document.document"].with_user(self.reader)

        def sql(domain):
            select = Document._search(domain, bypass_access=True).select()
            return select.code, select.params

        self.assertEqual(
            sql(Document._search_user_permission("not in", ["none"])),
            sql(Document._reach("view", False) & Document._access_label_reach("view")),
        )
