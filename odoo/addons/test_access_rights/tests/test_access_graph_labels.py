from odoo.exceptions import AccessError, ValidationError
from odoo.fields import Command
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestAccessGraphLabels(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Node = cls.env["test_access_right.graph_node"]
        cls.Grant = cls.env["test_access_right.graph_grant"]
        cls.confidential, cls.restricted = cls.env["ir.access.class"].create(
            [
                {"name": "test_access_rights.confidential"},
                {"name": "test_access_rights.restricted"},
            ]
        )
        readers = cls.env["res.groups"].create({"name": "Label readers"})
        writers = cls.env["res.groups"].create({"name": "Label writers"})
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
        cls.plain = new_test_user(cls.env, login="lbl_plain", groups="base.group_user")
        cls.reader = new_test_user(
            cls.env, login="lbl_reader", groups="base.group_user"
        )
        cls.writer = new_test_user(
            cls.env, login="lbl_writer", groups="base.group_user"
        )
        cls.reader.group_ids = [Command.link(readers.id)]
        cls.writer.group_ids = [Command.link(writers.id)]
        cls.users = cls.plain | cls.reader | cls.writer

        cls.root = cls.Node.create({"name": "root"})
        cls.labelled = cls.Node.create(
            {
                "name": "labelled",
                "parent_id": cls.root.id,
                "access_label_id": cls.confidential.id,
            }
        )
        cls.below = cls.Node.create({"name": "below", "parent_id": cls.labelled.id})
        cls.boundary = cls.Node.create(
            {"name": "boundary", "parent_id": cls.labelled.id, "is_boundary": True}
        )
        cls.locked = cls.Node.create(
            {
                "name": "locked",
                "parent_id": cls.below.id,
                "access_label_id": cls.restricted.id,
            }
        )
        cls.nodes = cls.root | cls.labelled | cls.below | cls.boundary | cls.locked
        cls.Grant.create(
            [
                {"node_id": node.id, "partner_id": user.partner_id.id, "role": "manage"}
                for node in (cls.root, cls.boundary)
                for user in cls.users
            ]
        )

    def roles(self, user):
        nodes = self.nodes.with_user(user).sudo()
        nodes.invalidate_recordset(["access_role"])
        computed = {node.name: node.access_role for node in nodes}
        searched = {}
        for role in (False, "view", "edit", "manage"):
            for node in (
                self.Node.with_user(user)
                .sudo()
                .search([("id", "in", self.nodes.ids), ("access_role", "=", role)])
            ):
                self.assertNotIn(node.name, searched, "a node sits in one band")
                searched[node.name] = role
        self.assertEqual(computed, searched)
        return computed

    def visible(self, user):
        found = self.Node.with_user(user).search([("id", "in", self.nodes.ids)])
        return set(found.mapped("name"))

    def test_a_label_reaches_below_it_live_within_its_scope(self):
        self.assertEqual(
            {node.name: node.access_inherited_label_id for node in self.nodes},
            {
                "root": self.env["ir.access.class"],
                "labelled": self.confidential,
                "below": self.confidential,
                "boundary": self.env["ir.access.class"],
                "locked": self.restricted,
            },
        )
        self.assertEqual(
            self.Node.search(
                [
                    ("id", "in", self.nodes.ids),
                    ("access_inherited_label_id", "=", self.confidential.id),
                ]
            ),
            self.labelled | self.below,
        )
        self.assertEqual(
            self.Node.search(
                [
                    ("id", "in", self.nodes.ids),
                    ("access_inherited_label_id", "=", False),
                ]
            ),
            self.root | self.boundary,
        )

    def test_the_label_guard_matrix(self):
        self.assertEqual(self.visible(self.plain), {"root", "boundary"})
        self.assertEqual(
            self.visible(self.reader), {"root", "labelled", "below", "boundary"}
        )
        self.assertEqual(
            self.visible(self.writer), {"root", "labelled", "below", "boundary"}
        )
        self.assertEqual(
            self.roles(self.plain),
            {
                "root": "manage",
                "labelled": False,
                "below": False,
                "boundary": "manage",
                "locked": False,
            },
        )
        self.assertEqual(
            self.roles(self.reader),
            {
                "root": "manage",
                "labelled": "view",
                "below": "view",
                "boundary": "manage",
                "locked": False,
            },
        )
        self.assertEqual(
            self.roles(self.writer),
            {
                "root": "manage",
                "labelled": "manage",
                "below": "manage",
                "boundary": "manage",
                "locked": False,
            },
        )
        with self.assertRaises(AccessError):
            self.below.with_user(self.reader).write({"name": "changed"})
        self.below.with_user(self.writer).write({"name": "changed"})
        self.assertEqual(self.below.name, "changed")

    def test_a_move_or_an_unlabel_counts_at_once(self):
        self.below.parent_id = self.root
        self.assertEqual(self.visible(self.plain), {"root", "below", "boundary"})
        self.labelled.access_label_id = False
        self.assertEqual(
            self.visible(self.plain), {"root", "labelled", "below", "boundary"}
        )

    def test_the_label_is_set_by_whoever_holds_the_top_role(self):
        editor = new_test_user(self.env, login="lbl_editor", groups="base.group_user")
        self.Grant.create(
            {
                "node_id": self.root.id,
                "partner_id": editor.partner_id.id,
                "role": "edit",
            }
        )
        with self.assertRaises(AccessError):
            self.root.with_user(editor).write({"access_label_id": self.confidential.id})
        with self.assertRaises(AccessError):
            self.Node.with_user(editor).create(
                {
                    "name": "new",
                    "parent_id": self.root.id,
                    "access_label_id": self.confidential.id,
                }
            )
        self.root.with_user(self.writer).write(
            {"access_label_id": self.confidential.id}
        )
        self.assertEqual(self.visible(self.plain), {"boundary"})

    def test_a_class_someone_writes_without_reading_cannot_label(self):
        write_only = self.env["ir.access.class"].create(
            {"name": "test_access_rights.write_only"}
        )
        self.env["ir.access"].create(
            {
                "name": "write_only: everyone writes",
                "class_id": write_only.id,
                "group_id": self.env.ref("base.group_everyone").id,
                "kind": "permission",
                "operation": "u",
            }
        )
        self.assertEqual(
            (write_only | self.confidential | self.restricted).filtered("can_label"),
            self.confidential | self.restricted,
        )
        with self.assertRaises(ValidationError):
            self.root.access_label_id = write_only
        self.assertEqual(
            self.visible(self.writer), {"root", "labelled", "below", "boundary"}
        )
