from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestScopedGrantFields(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env.company
        cls.company_b = cls.env["res.company"].create({"name": "Scoped fields B"})
        cls.user = new_test_user(
            cls.env,
            login="scoped_fields",
            groups="base.group_user",
            company_ids=[Command.set((cls.company_a | cls.company_b).ids)],
        )
        cls.env["res.users.grant"].create(
            {
                "user_id": cls.user.id,
                "group_id": cls.env.ref("test_access_rights.test_group").id,
                "company_ids": [Command.set(cls.company_a.ids)],
            }
        )
        cls.record_b = cls.env["test_access_right.some_obj"].create(
            {"val": 1, "company_id": cls.company_b.id, "forbidden2": 7}
        )

    def env_for(self, *companies):
        return self.env(
            user=self.user,
            context={"allowed_company_ids": [company.id for company in companies]},
        )

    def read_forbidden2(self, *companies):
        env = self.env_for(*companies)
        return env["test_access_right.some_obj"].browse(self.record_b.id).forbidden2

    def test_a_field_group_held_in_one_company_shows_the_field_there_only(self):
        # a field's groups= held through a grant limited to company A reads on
        # A's records: on B's it reads as empty, refuses attribute access, and
        # cannot be searched for
        record_a = self.env["test_access_right.some_obj"].create(
            {"val": 2, "company_id": self.company_a.id, "forbidden2": 5}
        )
        env = self.env_for(self.company_a, self.company_b)
        records = env["test_access_right.some_obj"].browse(
            (record_a | self.record_b).ids
        )
        self.assertEqual(
            {row["id"]: row["forbidden2"] for row in records.read(["forbidden2"])},
            {record_a.id: 5, self.record_b.id: False},
        )
        self.assertEqual(records[0].forbidden2, 5)
        with self.assertRaises(AccessError):
            self.read_forbidden2(self.company_a, self.company_b)
        self.assertFalse(
            env["test_access_right.some_obj"].search([("forbidden2", "=", 7)])
        )
        self.assertEqual(self.record_b.forbidden2, 7)

    def test_without_the_group_s_company_in_use_the_field_is_hidden(self):
        with self.assertRaises(AccessError):
            self.read_forbidden2(self.company_b)
