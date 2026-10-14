from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase

from odoo.addons.base.models.ir_access import filter_reads_user

MODEL = "test_ir_access.reached"


class TestReach(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.access"].search([("model_id.model", "=", MODEL)]).unlink()
        cls.group = cls.env["res.groups"].create({"name": "Reach"})
        cls.parent = cls.env["res.company"].create({"name": "Parent"})
        cls.child = cls.env["res.company"].create(
            {"name": "Child", "parent_id": cls.parent.id}
        )
        cls.other = cls.env["res.company"].create({"name": "Other"})
        cls.customer = cls.env["res.partner"].create(
            {"name": "Customer", "is_company": True}
        )
        cls.contact = cls.env["res.partner"].create(
            {"name": "Contact", "parent_id": cls.customer.id}
        )
        cls.user = cls.env["res.users"].create(
            {
                "login": "reacher",
                "name": "Reacher",
                "company_id": cls.child.id,
                "company_ids": [Command.set(cls.child.ids)],
                "group_ids": [
                    Command.set((cls.env.ref("base.group_user") + cls.group).ids)
                ],
            }
        )
        cls.user.partner_id.parent_id = cls.customer
        cls.stranger = cls.env["res.users"].create(
            {"login": "stranger", "name": "Stranger"}
        )
        Reached = cls.env[MODEL]
        cls.mine = Reached.create({"name": "mine", "user_id": cls.user.id})
        cls.theirs = Reached.create({"name": "theirs", "user_id": cls.stranger.id})
        cls.nobody = Reached.create({"name": "nobody"})
        cls.approving = Reached.create(
            {"name": "approving", "approver_ids": [Command.link(cls.user.id)]}
        )
        cls.my_partner = Reached.create(
            {"name": "my partner", "partner_id": cls.user.partner_id.id}
        )
        cls.colleague = Reached.create(
            {"name": "colleague", "partner_id": cls.contact.id}
        )
        cls.in_child = Reached.create({"name": "child", "company_id": cls.child.id})
        cls.in_parent = Reached.create({"name": "parent", "company_id": cls.parent.id})
        cls.in_other = Reached.create({"name": "other", "company_id": cls.other.id})
        cls.all = Reached.search([])

    def row(self, reach, anchor=None, domain=None, **values):
        return self.env["ir.access"].create(
            {
                "name": f"reach {reach}",
                "model_id": self.env["ir.model"]._get_id(MODEL),
                "group_id": self.group.id,
                "kind": "permission",
                "operation": "r",
                "reach": reach,
                "anchor": anchor,
                "domain": domain,
                **values,
            }
        )

    def reached(self):
        return self.env[MODEL].with_user(self.user).search([]) & self.all

    def test_own_reads_the_owner(self):
        self.row("own")
        self.assertEqual(self.reached(), self.mine)

    def test_a_shared_anchor_admits_the_unassigned(self):
        self.row("own", "assignee")
        self.assertEqual(self.reached(), self.all - self.theirs)

    def test_own_through_a_second_anchor(self):
        self.row("own", "approver")
        self.assertEqual(self.reached(), self.approving)

    def test_several_records_move_through_a_many2many_anchor_in_one_write(self):
        self.row("all", operation="cru")
        records = self.nobody + self.in_child

        records.with_user(self.user).write(
            {"approver_ids": [Command.link(self.stranger.id)]}
        )

        self.assertEqual(records.mapped("approver_ids"), self.stranger)

    def test_own_through_the_creator(self):
        mine = self.env[MODEL].with_user(self.user).sudo().create({"name": "created"})
        self.row("own", "creator")
        self.assertEqual(self.env[MODEL].with_user(self.user).search([]), mine)

    def test_anchor_snapshots_only_read_triggered_fields_and_skip_elevated_records(
        self,
    ):
        self.row("all", operation="r")
        records = self.mine.with_user(self.user)
        before = records._get_anchor_values_before_write({"user_id": self.stranger.id})
        self.assertEqual(before, {"user_id": {self.mine.id: self.user.id}})
        self.assertEqual(self.mine.user_id, self.user)
        with self.assertQueryCount(0):
            self.assertIsNone(records._get_anchor_values_before_write({"name"}))
            self.assertIsNone(
                records.browse()._get_anchor_values_before_write({"user_id"})
            )
            self.assertIsNone(
                records.sudo()._get_anchor_values_before_write({"user_id"})
            )
        virtual = self.env[MODEL].new({"user_id": self.user.id}).with_user(self.user)
        self.assertEqual(
            virtual._get_anchor_values_before_write({"user_id"}), {"user_id": {}}
        )

    def test_changed_anchor_ids_are_sorted_deduplicated_and_do_not_enforce_access(self):
        records = self.mine | self.theirs
        before = {
            "user_id": {self.theirs.id: self.user.id, self.mine.id: self.stranger.id},
            "company_id": {self.mine.id: self.child.id},
        }
        self.assertEqual(
            records.with_user(self.user)._get_ids_with_changed_anchors(before),
            tuple(sorted(records.ids)),
        )
        self.assertEqual(records.mapped("user_id"), self.user | self.stranger)
        with self.assertQueryCount(0):
            self.assertEqual(records._get_ids_with_changed_anchors({}), ())
            self.assertEqual(
                records._get_ids_with_changed_anchors({"not_a_field": {}}), ()
            )

    def test_a_write_cannot_move_an_owned_record_outside_its_destination_permissions(
        self,
    ):
        self.row("all", operation="r")
        self.row("own", operation="u")
        record = self.mine.with_user(self.user)
        with self.assertRaises(AccessError):
            record.write({"user_id": self.stranger.id})
        self.assertEqual(self.mine.user_id, self.user)
        self.row("all", operation="c")
        record.write({"user_id": self.stranger.id})
        self.assertEqual(self.mine.user_id, self.stranger)

    def test_anchor_access_ignores_unchanged_records_in_a_batch(self):
        self.row("all", operation="r")
        self.row("own", operation="u")
        records = (self.mine | self.theirs).with_user(self.user)
        before = {
            "user_id": {self.mine.id: self.user.id, self.theirs.id: self.stranger.id}
        }
        records._check_anchor_move_access(before)
        before["user_id"][self.mine.id] = self.stranger.id
        records._check_anchor_move_access(before)
        before["user_id"][self.theirs.id] = self.user.id
        with self.assertRaises(AccessError):
            records._check_anchor_move_access(before)

    def test_own_through_the_partner_is_the_principal_s_own_contact(self):
        self.row("own", "partner")
        self.assertEqual(self.reached(), self.my_partner)

    def test_partner_reads_the_commercial_tree(self):
        self.row("partner")
        self.assertEqual(self.reached(), self.my_partner + self.colleague)

    def test_company_reads_the_companies_in_use_and_the_shared_records(self):
        self.row("company")
        self.assertEqual(self.reached(), self.all - self.in_parent - self.in_other)

    def test_a_company_anchor_can_read_up_the_tree(self):
        self.row("company", "parent_company")
        self.assertEqual(self.reached(), self.in_child + self.in_parent)

    def test_all_and_none(self):
        self.row("all")
        self.assertEqual(self.reached(), self.all)
        self.env["ir.access"].search([("model_id.model", "=", MODEL)]).unlink()
        self.row("none")
        self.assertFalse(self.env[MODEL].with_user(self.user).has_access("read"))

    def test_a_fixed_filter_rides_along(self):
        self.row("own", "assignee", domain="[('name', '!=', 'nobody')]")
        self.assertEqual(self.reached(), self.all - self.theirs - self.nobody)

    def test_a_template_predicate(self):
        predicate = self.env["ir.access.predicate"].create(
            {
                "name": "test.named_by",
                "template": "[('name', '=', args.name), ('user_id', 'in', [P.user])]",
            }
        )
        self.row(
            "predicate", predicate_id=predicate.id, predicate_args={"name": "mine"}
        )
        self.assertEqual(self.reached(), self.mine)

    def test_a_method_predicate(self):
        predicate = self.env["ir.access.predicate"].create(
            {
                "name": "test.named",
                "model_id": self.env["ir.model"]._get_id(MODEL),
                "method": "_access_predicate_named",
            }
        )
        self.row(
            "predicate", predicate_id=predicate.id, predicate_args={"name": "theirs"}
        )
        self.assertEqual(self.reached(), self.theirs)

    def test_a_row_passes_its_predicate_the_arguments_it_reads(self):
        template = self.env["ir.access.predicate"].create(
            {
                "name": "test.named_at",
                "template": "[(args.at + 'name', '=', args.name)]",
            }
        )
        method = self.env["ir.access.predicate"].create(
            {
                "name": "test.named",
                "model_id": self.env["ir.model"]._get_id(MODEL),
                "method": "_access_predicate_named",
            }
        )
        for predicate, args in (
            (template, {"at": ""}),
            (template, {"at": "", "name": "mine", "exempt": ["base.group_user"]}),
            (method, {}),
            (method, {"name": "theirs", "role": "base.group_user"}),
            (method, ["name"]),
        ):
            with self.subTest(predicate=predicate.name, args=args):
                with self.assertRaisesRegex(ValidationError, "it reads|are named"):
                    self.row(
                        "predicate", predicate_id=predicate.id, predicate_args=args
                    )
        row = self.row(
            "predicate", predicate_id=method.id, predicate_args={"name": "theirs"}
        )
        with self.assertRaisesRegex(ValidationError, "it reads name"):
            row.predicate_args = {"nom": "theirs"}
        self.row(
            "predicate",
            predicate_id=template.id,
            predicate_args={"at": "", "name": "mine"},
        )
        with self.assertRaisesRegex(ValidationError, "it reads at, label"):
            template.template = "[(args.at + 'name', '=', args.label)]"
        conditional = self.env.ref("base.access_predicate_conditional_reach")
        self.assertEqual(
            conditional._arguments(MODEL),
            (frozenset({"operation", "role"}), frozenset({"with"})),
        )

    def test_a_predicate_rewritten_while_modules_load_leaves_rows_not_loaded(self):
        ceiling = self.env.ref("base.access_predicate_conditional_reach")
        self.row(
            "predicate",
            predicate_id=ceiling.id,
            predicate_args={"operation": "read", "role": "base.group_user"},
        )
        registry = self.env.registry
        with patch.dict(registry.models):
            del registry.models[MODEL]
            ceiling.write({"method": ceiling.method})
        self.assertEqual(ceiling.method, "_access_predicate_conditional_reach")

    def test_the_explanation_says_the_reach(self):
        self.row("own", "approver")
        lines = self.env["ir.access"].with_user(self.user)._explain(MODEL, "read")
        self.assertTrue(any("approver_ids" in line for line in lines), lines)

    def test_the_explanation_says_a_row_reaching_nothing_grants_nothing(self):
        self.row("none")
        lines = self.env["ir.access"].with_user(self.user)._explain(MODEL, "read")
        self.assertTrue(any("(nothing)" in line for line in lines), lines)

    def test_an_anchor_the_model_does_not_declare_is_refused(self):
        with self.assertRaisesRegex(ValidationError, "does not declare"):
            self.row("team")

    def test_a_rung_that_cannot_read_the_anchor_is_refused(self):
        with self.assertRaisesRegex(ValidationError, "cannot read the anchor"):
            self.row("partner", "owner")

    def test_beside_a_reach_the_domain_reads_no_user(self):
        with self.assertRaisesRegex(ValidationError, "fixed filter"):
            self.row("own", domain="[('user_id', '=', user.id)]")

    def test_beside_a_reach_a_filter_naming_fixed_records_is_a_fixed_filter(self):
        admins = self.env[MODEL].create(
            {"name": "admin's", "partner_id": self.env.ref("base.partner_admin").id}
        )
        self.row("all", domain="[('partner_id', '=', ref('base.partner_admin'))]")
        self.assertEqual(self.env[MODEL].with_user(self.user).search([]), admins)

    def test_a_predicate_is_its_own_reach(self):
        predicate = self.env["ir.access.predicate"].create(
            {"name": "test.any", "template": "[]"}
        )
        with self.assertRaisesRegex(ValidationError, "Named predicate"):
            self.row("own", predicate_id=predicate.id)
        with self.assertRaisesRegex(ValidationError, "Named predicate"):
            self.row("predicate")

    def test_a_template_reads_only_the_principal_and_its_arguments(self):
        Predicate = self.env["ir.access.predicate"]
        with self.assertRaisesRegex(ValidationError, "reads only P and args"):
            Predicate.create({"name": "t1", "template": "[('id', '=', user.id)]"})
        with self.assertRaisesRegex(ValidationError, "the principal offers"):
            Predicate.create({"name": "t2", "template": "[('id', '=', P.password)]"})

    def test_the_anchors_are_checked_against_the_registry(self):
        anchors = self.env.registry.model_anchors[MODEL]
        self.assertEqual(anchors["approver"].kind, "owner")
        self.assertEqual(anchors["creator"].path, "create_uid")
        self.assertEqual(self.env[MODEL]._get_company_anchor_path(), "company_id")

    def test_a_filter_on_a_field_that_reads_the_user_is_no_fixed_filter(self):
        registry = self.env.registry
        self.assertTrue(filter_reads_user(registry, MODEL, "[('is_mine', '=', True)]"))
        self.assertFalse(filter_reads_user(registry, MODEL, "[('name', '=', 'x')]"))
        self.assertTrue(
            filter_reads_user(
                registry, MODEL, "[('is_mine', '=', ref('base.user_root'))]"
            )
        )
        with self.assertRaises(ValidationError):
            self.row("all", domain="[('is_mine', '=', True)]")
        row = self.row("all", domain="[('name', '!=', False)]")
        self.env.cr.execute(
            "UPDATE ir_access SET domain = %s WHERE id = %s",
            ["[('is_mine', '=', True)]", row.id],
        )
        row.invalidate_recordset()
        self.env["ir.access"]._clear_access_caches()
        self.assertEqual(self.reached(), self.mine)

    def test_a_company_reach_refusal_suggests_the_record_s_company(self):
        self.user.company_ids += self.other
        self.row("all")
        self.row("company", kind="guard", guard_scope="members")
        record = self.in_other.with_user(self.user).with_context(
            allowed_company_ids=self.child.ids
        )
        with self.assertRaises(AccessError) as caught:
            record.check_access("read")
        self.assertIn("switching to the company: Other", caught.exception.args[0])
        self.assertEqual(
            caught.exception.context["suggested_company"]["id"], self.other.id
        )

    def test_a_refusal_is_explained_for_the_contact_acted_for(self):
        self.row("all")
        self.row("own", "partner", kind="guard", guard_scope="members", name="own")
        record = self.my_partner.with_user(self.user).with_acting_partner(self.contact)
        with self.assertRaisesRegex(AccessError, "Refused by: own"):
            record.check_access("read")
