from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user

MODEL = "test_ir_access.classified"


class TestFieldClassScopes(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env.company
        cls.company_b = cls.env["res.company"].create({"name": "Field scope B"})
        cls.pay_group = cls.env["res.groups"].create({"name": "Scoped pay readers"})
        cls.blocked_group = cls.env["res.groups"].create({"name": "Pay blocked"})
        pay = cls.env["ir.access.class"].create({"name": "test_ir_access.pay"})
        cls.env["ir.access.class"].create({"name": "test_ir_access.pay_write"})
        cls.env["ir.access"].create(
            [
                {
                    "name": "pay: scoped readers",
                    "class_id": pay.id,
                    "group_id": cls.pay_group.id,
                    "kind": "permission",
                    "operation": "ru",
                },
                {
                    "name": "pay: blocked",
                    "class_id": pay.id,
                    "group_id": cls.blocked_group.id,
                    "kind": "guard",
                    "guard_scope": "members",
                    "operation": "ru",
                    "reach": "none",
                },
            ]
        )
        companies = cls.company_a | cls.company_b
        cls.user = new_test_user(
            cls.env,
            login="fs_scoped",
            groups="base.group_user,base.group_allow_export",
            company_ids=[Command.set(companies.ids)],
        )
        cls.env["res.users.grant"].create(
            {
                "user_id": cls.user.id,
                "group_id": cls.pay_group.id,
                "company_ids": [Command.set(cls.company_a.ids)],
            }
        )
        cls.unscoped = new_test_user(
            cls.env,
            login="fs_unscoped",
            groups="base.group_user",
            company_ids=[Command.set(companies.ids)],
        )
        cls.unscoped.group_ids += cls.pay_group
        records = cls.env[MODEL].create(
            [
                {"name": "A", "wage": 10.0, "company_id": cls.company_a.id},
                {"name": "B", "wage": 20.0, "company_id": cls.company_b.id},
                {"name": "S", "wage": 30.0},
            ]
        )
        cls.rec_a, cls.rec_b, cls.rec_s = records
        cls.records = records

    def as_user(self, user=None, records=None):
        companies = self.company_a | self.company_b
        env = self.env(
            user=user or self.user,
            context={"allowed_company_ids": companies.ids},
        )
        return (records or self.records).with_env(env)

    def test_read_masks_the_value_outside_the_grant_companies(self):
        values = {
            row["name"]: row["wage"] for row in self.as_user().read(["name", "wage"])
        }
        self.assertEqual(values, {"A": 10.0, "B": False, "S": 30.0})

    def test_a_masked_relational_field_reads_as_empty(self):
        partner = self.env["res.partner"].create({"name": "Payee"})
        self.records.payee_ids = partner
        rows = self.as_user().read(["name", "payee_ids"])
        self.assertEqual(
            {row["name"]: row["payee_ids"] for row in rows},
            {"A": partner.ids, "B": [], "S": partner.ids},
        )

    def test_attribute_access_refuses_outside_and_reads_inside(self):
        self.assertEqual(self.as_user(records=self.rec_a).wage, 10.0)
        with self.assertRaises(AccessError):
            _ = self.as_user(records=self.rec_b).wage
        with self.assertRaises(AccessError):
            self.as_user().mapped("wage")

    def test_the_cache_keeps_the_true_value(self):
        self.as_user().read(["wage"])
        self.assertEqual(self.rec_b.wage, 20.0)
        self.assertEqual(self.as_user(records=self.rec_b).sudo().wage, 20.0)

    def test_search_sort_and_group_cannot_probe_the_value(self):
        Model = self.as_user().browse()
        self.assertFalse(Model.search([("wage", "=", 20.0)]))
        self.assertEqual(Model.search([("wage", "=", 10.0)]), self.rec_a)
        found = Model.search([("id", "in", self.records.ids)], order="wage, id")
        self.assertEqual(found.ids, (self.rec_a | self.rec_s | self.rec_b).ids)
        [(total,)] = Model._read_group(
            [("id", "in", self.records.ids)], aggregates=["wage:sum"]
        )
        self.assertEqual(total, 40.0)

    def test_write_and_create_are_refused_outside(self):
        self.as_user(records=self.rec_a).write({"wage": 11.0})
        self.assertEqual(self.rec_a.wage, 11.0)
        with self.assertRaises(AccessError):
            self.as_user(records=self.rec_b).write({"wage": 21.0})
        Model = self.as_user().browse()
        Model.create({"name": "A2", "wage": 1.0, "company_id": self.company_a.id})
        with self.assertRaises(AccessError):
            Model.create({"name": "B2", "wage": 1.0, "company_id": self.company_b.id})

    def test_a_field_attachment_is_reached_inside_the_grant_only(self):
        self.records.payslip = b"cGF5"
        Attachment = self.env["ir.attachment"]
        attachments = {
            record: Attachment.search(
                [
                    ("res_model", "=", MODEL),
                    ("res_field", "=", "payslip"),
                    ("res_id", "=", record.id),
                ]
            )
            for record in self.records
        }
        UserAttachment = Attachment.with_env(self.as_user().env)
        found = UserAttachment.search(
            [
                ("res_model", "=", MODEL),
                ("res_field", "=", "payslip"),
                ("res_id", "in", self.records.ids),
            ]
        )
        self.assertEqual(found, attachments[self.rec_a] | attachments[self.rec_s])
        UserAttachment.browse(attachments[self.rec_a].ids).read(["datas"])
        with self.assertRaises(AccessError):
            UserAttachment.browse(attachments[self.rec_b].ids).read(["datas"])
        with self.assertRaises(AccessError):
            UserAttachment.browse(attachments[self.rec_b].ids).write({"name": "x"})

    def test_moving_a_field_attachment_keeps_the_grant(self):
        self.rec_a.payslip = b"cGF5"
        attachment = self.env["ir.attachment"].search(
            [
                ("res_model", "=", MODEL),
                ("res_field", "=", "payslip"),
                ("res_id", "=", self.rec_a.id),
            ]
        )
        UserAttachment = attachment.with_env(self.as_user().env)
        with self.assertRaises(AccessError):
            UserAttachment.write({"res_id": self.rec_b.id})
        loose = (
            self.env["ir.attachment"]
            .with_env(self.as_user().env)
            .create(
                {
                    "name": "loose",
                    "raw": b"x",
                    "res_model": MODEL,
                    "res_id": self.rec_a.id,
                }
            )
        )
        with self.assertRaises(AccessError):
            loose.write({"res_id": self.rec_b.id, "res_field": "payslip"})

    def test_a_field_attachment_of_an_archived_record_is_found_as_it_is_read(self):
        self.records.payslip = b"cGF5"
        self.rec_a.active = False
        UserAttachment = self.env["ir.attachment"].with_env(self.as_user().env)
        found = UserAttachment.search(
            [
                ("res_model", "=", MODEL),
                ("res_field", "=", "payslip"),
                ("res_id", "in", self.records.ids),
            ]
        )
        readable = UserAttachment.browse(
            self.env["ir.attachment"]
            .search(
                [
                    ("res_model", "=", MODEL),
                    ("res_field", "=", "payslip"),
                    ("res_id", "in", self.records.ids),
                ]
            )
            .ids
        )._filtered_access("read")
        self.assertEqual(found, readable)
        self.assertIn(self.rec_a.id, found.mapped("res_id"))

    def test_export_masks_the_value_outside(self):
        records = self.as_user().sorted("name")
        rows = records.with_context(import_compat=False).export_data(["name", "wage"])
        self.assertEqual([row[1] for row in rows["datas"]], [10.0, False, 30.0])

    def test_a_guard_held_in_one_company_refuses_there_only(self):
        self.env["res.users.grant"].create(
            {
                "user_id": self.unscoped.id,
                "group_id": self.blocked_group.id,
                "company_ids": [Command.set(self.company_b.ids)],
            }
        )
        values = {
            row["name"]: row["wage"]
            for row in self.as_user(self.unscoped).read(["name", "wage"])
        }
        self.assertEqual(values, {"A": 10.0, "B": False, "S": False})

    def test_an_unscoped_principal_pays_no_mask(self):
        Model = self.as_user(self.unscoped).browse()
        query = Model._search([("wage", "=", 20.0)])
        self.assertNotIn("CASE WHEN", query.where_clause.code)
        self.assertEqual(Model.search([("wage", "=", 20.0)]), self.rec_b)
        scoped = self.as_user().browse()._search([("wage", "=", 20.0)])
        self.assertIn("CASE WHEN", scoped.where_clause.code)
