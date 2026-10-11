from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import TransactionCase, new_test_user, tagged

MODEL = "test_access_right.some_obj"


@tagged("post_install", "-at_install")
class TestFieldVerdictMemo(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env.company
        cls.company_b = cls.env["res.company"].create({"name": "Verdict memo B"})
        companies = cls.company_a | cls.company_b
        cls.user = new_test_user(
            cls.env,
            login="verdict_memo",
            groups="base.group_user",
            company_ids=[Command.set(companies.ids)],
        )
        cls.other = new_test_user(
            cls.env,
            login="verdict_memo_other",
            groups="base.group_user",
            company_ids=[Command.set(companies.ids)],
        )
        group = cls.env.ref("test_access_rights.test_group")
        cls.env["res.users.grant"].create(
            [
                {
                    "user_id": cls.user.id,
                    "group_id": group.id,
                    "company_ids": [Command.set(cls.company_a.ids)],
                },
                {
                    "user_id": cls.other.id,
                    "group_id": group.id,
                    "company_ids": [Command.set(cls.company_b.ids)],
                },
            ]
        )

    def as_user(self, records, user=None):
        env = self.env(
            user=user or self.user,
            context={"allowed_company_ids": (self.company_a | self.company_b).ids},
        )
        return records.with_env(env)

    def readable(self, record):
        try:
            record.forbidden2
        except AccessError:
            return False
        return True

    def test_reading_the_field_over_many_records_judges_them_at_once(self):
        records = self.env[MODEL].create(
            [
                {
                    "val": i,
                    "forbidden2": i,
                    "company_id": (self.company_a if i % 2 else self.company_b).id,
                }
                for i in range(200)
            ]
        )
        user_records = self.as_user(records)
        model_cls = type(self.env[MODEL])
        original = model_cls.filtered_domain
        judged = []

        def filtered_domain(records, domain):
            if "company_id" in str(domain):
                judged.append(len(records))
            return original(records, domain)

        with patch.object(model_cls, "filtered_domain", filtered_domain):
            seen = [self.readable(record) for record in user_records]
        self.assertEqual(seen, [bool(i % 2) for i in range(200)])
        self.assertEqual(judged, [200])

    def test_a_write_of_the_company_flips_the_verdict_both_ways(self):
        record = self.env[MODEL].create(
            {"val": 1, "forbidden2": 7, "company_id": self.company_b.id}
        )
        user_record = self.as_user(record)
        self.assertFalse(self.readable(user_record))
        record.company_id = self.company_a
        self.assertTrue(self.readable(user_record))
        self.assertEqual(user_record.read(["forbidden2"])[0]["forbidden2"], 7)
        record.company_id = self.company_b
        self.assertFalse(self.readable(user_record))
        self.assertFalse(user_record.read(["forbidden2"])[0]["forbidden2"])

    def test_an_sql_write_and_its_invalidation_flip_the_verdict(self):
        record = self.env[MODEL].create(
            {"val": 1, "forbidden2": 7, "company_id": self.company_b.id}
        )
        user_record = self.as_user(record)
        self.assertFalse(self.readable(user_record))
        self.env.cr.execute(
            "UPDATE test_access_right_some_obj SET company_id = %s WHERE id = %s",
            (self.company_a.id, record.id),
        )
        record.invalidate_recordset(["company_id"])
        self.assertTrue(self.readable(user_record))

    def test_principals_do_not_share_verdicts(self):
        record = self.env[MODEL].create(
            {"val": 1, "forbidden2": 7, "company_id": self.company_a.id}
        )
        self.assertTrue(self.readable(self.as_user(record)))
        self.assertFalse(self.readable(self.as_user(record, self.other)))
        record.company_id = self.company_b
        self.assertFalse(self.readable(self.as_user(record)))
        self.assertTrue(self.readable(self.as_user(record, self.other)))

    def test_resequencing_a_field_is_refused_on_records_outside_its_grant(self):
        mine, theirs = self.env[MODEL].create(
            [
                {"val": 1, "forbidden2": 1, "company_id": self.company_a.id},
                {"val": 2, "forbidden2": 2, "company_id": self.company_b.id},
            ]
        )
        with self.assertRaises(AccessError):
            self.as_user(mine | theirs).web_resequence({}, "forbidden2")
        self.as_user(mine).web_resequence({}, "forbidden2", offset=7)
        self.assertEqual(mine.forbidden2, 7)
        self.assertEqual(theirs.forbidden2, 2)
