from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user

MODEL = "test_ir_access.labelled"


class TestRecordLabels(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.confidential, cls.restricted = cls.env["ir.access.class"].create(
            [
                {"name": "test_ir_access.confidential"},
                {"name": "test_ir_access.restricted"},
            ]
        )
        cls.readers = cls.env["res.groups"].create({"name": "Confidential readers"})
        cls.writers = cls.env["res.groups"].create({"name": "Confidential writers"})
        cls.env["ir.access"].create(
            [
                {
                    "name": "confidential: readers read",
                    "class_id": cls.confidential.id,
                    "group_id": cls.readers.id,
                    "kind": "permission",
                    "operation": "r",
                },
                {
                    "name": "confidential: writers write",
                    "class_id": cls.confidential.id,
                    "group_id": cls.writers.id,
                    "kind": "permission",
                    "operation": "ru",
                },
            ]
        )
        cls.user = new_test_user(cls.env, login="lbl_user", groups="base.group_user")
        cls.open, cls.secret, cls.locked = cls.env[MODEL].create(
            [
                {"name": "open"},
                {"name": "secret", "label_id": cls.confidential.id},
                {"name": "locked", "label_id": cls.restricted.id},
            ]
        )
        cls.records = cls.open | cls.secret | cls.locked

    def visible(self, user):
        return self.env[MODEL].with_user(user).search([("id", "in", self.records.ids)])

    def test_a_label_hides_the_record_from_those_its_class_does_not_grant(self):
        self.assertEqual(self.visible(self.user), self.open)
        with self.assertRaises(AccessError):
            self.secret.with_user(self.user).read(["name"])

    def test_the_class_s_readers_reach_the_record_and_only_read_it(self):
        self.user.group_ids += self.readers
        self.assertEqual(self.visible(self.user), self.open | self.secret)
        self.assertEqual(self.secret.with_user(self.user).name, "secret")
        with self.assertRaises(AccessError):
            self.secret.with_user(self.user).write({"name": "changed"})

    def test_the_class_s_writers_change_the_record(self):
        self.user.group_ids = [Command.link(self.writers.id)]
        self.secret.with_user(self.user).write({"name": "changed"})
        self.assertEqual(self.secret.name, "changed")

    def test_a_class_without_rows_reaches_no_one_but_the_superuser(self):
        self.user.group_ids += self.readers | self.writers
        self.assertNotIn(self.locked, self.visible(self.user))
        self.assertEqual(self.locked.sudo().name, "locked")

    def test_a_refusal_by_the_label_names_the_label(self):
        secret = self.secret.with_user(self.user)
        with self.assertRaisesRegex(AccessError, f"Refused by: the label of {MODEL}"):
            secret.check_access("read")
        explanation = (
            self.env["ir.access"].with_user(self.user)._explain_record(secret, "read")
        )
        self.assertFalse(explanation["allowed"])
        self.assertEqual(
            [guard["name"] for guard in explanation["guards"] if not guard["admits"]],
            [f"the label of {MODEL}"],
        )

    def test_a_label_change_counts_at_once(self):
        self.secret.label_id = False
        self.assertIn(self.secret, self.visible(self.user))
