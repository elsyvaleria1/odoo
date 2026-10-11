from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user

MODEL = "test_ir_access.profile"


class TestFieldClassHooks(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        own, locked = cls.env["ir.access.class"].create(
            [{"name": "test_ir_access.own"}, {"name": "test_ir_access.locked"}]
        )
        cls.locked_group = cls.env["res.groups"].create({"name": "Note locked"})
        cls.spared_group = cls.env["res.groups"].create({"name": "Note spared"})
        everyone = cls.env.ref("base.group_everyone")
        cls.rows = cls.env["ir.access"].create(
            [
                {
                    "name": "own: everyone reads their own",
                    "class_id": own.id,
                    "group_id": everyone.id,
                    "kind": "permission",
                    "operation": "r",
                    "reach": "own",
                },
                {
                    "name": "locked: everyone writes",
                    "class_id": locked.id,
                    "group_id": everyone.id,
                    "kind": "permission",
                    "operation": "u",
                },
                {
                    "name": "locked: not the locked group",
                    "class_id": locked.id,
                    "group_id": cls.locked_group.id,
                    "kind": "guard",
                    "guard_scope": "members",
                    "operation": "u",
                    "reach": "none",
                    "exempt_group_ids": [Command.link(cls.spared_group.id)],
                },
            ]
        )
        cls.alice = new_test_user(cls.env, login="fh_alice", groups="base.group_user")
        cls.bob = new_test_user(cls.env, login="fh_bob", groups="base.group_user")
        cls.admin = cls.env.ref("base.user_admin")
        cls.mine, cls.theirs = cls.env[MODEL].create(
            [
                {"name": "A", "user_id": cls.alice.id, "salary": 10.0},
                {"name": "B", "user_id": cls.bob.id, "salary": 20.0},
            ]
        )

    def test_an_owner_reads_their_own_field_and_no_one_else_s(self):
        records = (self.mine | self.theirs).with_user(self.alice)
        self.assertEqual(
            {row["name"]: row["salary"] for row in records.read(["name", "salary"])},
            {"A": 10.0, "B": False},
        )
        self.assertEqual(self.mine.with_user(self.alice).salary, 10.0)
        with self.assertRaises(AccessError):
            _ = self.theirs.with_user(self.alice).salary
        self.assertEqual(
            records.search([("salary", ">", 0)]), self.mine.with_user(self.alice)
        )

    def test_the_field_s_own_groups_still_read_every_record(self):
        records = (self.mine | self.theirs).with_user(self.admin)
        self.assertEqual(records.mapped("salary"), [10.0, 20.0])

    def test_without_the_alternative_row_the_owner_reads_nothing(self):
        self.rows[0].active = False
        with self.assertRaises(AccessError):
            self.mine.with_user(self.alice).read(["salary"])

    def test_a_write_class_guard_binds_its_members_and_spares_the_exempt(self):
        self.mine.with_user(self.alice).write({"note": "free"})
        self.alice.group_ids += self.locked_group
        with self.assertRaises(AccessError):
            self.mine.with_user(self.alice).write({"note": "locked"})
        self.mine.with_user(self.alice).write({"name": "still writes the rest"})
        self.alice.group_ids += self.spared_group
        self.mine.with_user(self.alice).write({"note": "spared"})
        self.assertEqual(self.mine.note, "spared")

    def test_the_model_s_class_adds_to_the_field_s_own(self):
        badge, holders = self.env["ir.access.class"].create(
            [
                {"name": "test_ir_access.badge"},
                {"name": "test_ir_access.badge_holders"},
            ]
        )
        readers = self.env["res.groups"].create({"name": "Badge readers"})
        holding = self.env["res.groups"].create({"name": "Badge holders"})
        self.env["ir.access"].create(
            [
                {
                    "name": f"{access_class.name}: {group.name}",
                    "class_id": access_class.id,
                    "group_id": group.id,
                    "kind": "permission",
                    "operation": "r",
                }
                for access_class, group in ((badge, readers), (holders, holding))
            ]
        )
        field = self.env[MODEL]._fields["badge"]
        self.assertEqual(
            field.access_classes.read,
            ("test_ir_access.badge", "test_ir_access.badge_holders"),
        )
        profiles = self.env[MODEL].with_user(self.alice)
        self.alice.group_ids += readers
        self.assertFalse(profiles._has_field_access(field, "read"))
        self.alice.group_ids += holding
        self.assertTrue(profiles._has_field_access(field, "read"))

    def test_a_class_row_reaches_through_an_anchor_every_model_declares(self):
        with self.assertRaises(ValidationError):
            self.env["ir.access"].create(
                {
                    "name": "locked: a team reach profile has no anchor for",
                    "class_id": self.rows[1].class_id.id,
                    "group_id": self.env.ref("base.group_everyone").id,
                    "kind": "permission",
                    "operation": "u",
                    "reach": "team",
                }
            )

    def test_only_a_class_guard_spares_groups(self):
        with self.assertRaises(ValidationError):
            self.rows[1].exempt_group_ids = [Command.link(self.spared_group.id)]
