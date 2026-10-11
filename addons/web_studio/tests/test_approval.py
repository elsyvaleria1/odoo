from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.mail.tests.common import mail_new_test_user


class StudioApprovalCase(TransactionCase):
    """Studio's approval rules, as the steps and bindings its editor now writes."""

    MODEL = "res.partner"
    METHOD = "address_get"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        creation_context = {
            "studio": True,
            "no_reset_password": True,
            "mail_create_nosubscribe": True,
            "mail_create_nolog": True,
        }
        Groups = cls.env["res.groups"].with_context(**creation_context)
        cls.group_user = Groups.create(
            {
                "name": "Approval User",
                "implied_ids": [Command.link(cls.env.ref("base.group_user").id)],
            }
        )
        cls.group_manager = Groups.create(
            {
                "name": "Approval Manager",
                "implied_ids": [Command.link(cls.group_user.id)],
            }
        )
        groups = "base.group_user,base.group_partner_manager"
        cls.user = mail_new_test_user(
            cls.env, login="Employee", groups=groups, context=creation_context
        )
        cls.manager = mail_new_test_user(
            cls.env, login="Manager", groups=groups, context=creation_context
        )
        cls.user.write({"group_ids": [Command.link(cls.group_user.id)]})
        cls.manager.write({"group_ids": [Command.link(cls.group_manager.id)]})
        cls.record = cls.user.partner_id
        cls.Binding = cls.env["approval.binding"]
        cls.Step = cls.env["approval.category.step"]

    def setUp(self):
        super().setUp()
        self.addCleanup(self.Binding._unregister_hook)

    def _button(self, method, action_id):
        if method is None and not action_id:
            method = self.METHOD
        return method or False, action_id or False

    def _step(self, method=None, action_id=False, **vals):
        method, action_id = self._button(method, action_id)
        step = self.Step.browse(
            self.Binding.create_step_for_button(self.MODEL, method, action_id)
        )
        step.write(
            {
                "name": "You didn't say the magic word!",
                "group_id": self.group_manager.id,
                **vals,
            }
        )
        return step

    def _request(self, step, record=None):
        binding = self.Binding.search([("category_id", "=", step.category_id.id)])
        return self.env["approval.request"].search(
            [
                ("binding_id", "=", binding.id),
                ("res_id", "=", (record or self.record).id),
            ],
            order="id desc",
            limit=1,
        )

    def _check(self, user, record=None, method=None, action_id=False):
        method, action_id = self._button(method, action_id)
        return self.Binding.with_user(user).check_button_approval(
            self.MODEL, (record or self.record).id, method, action_id
        )["approved"]

    def _decide(self, user, approve=True, record=None, method=None, action_id=False):
        method, action_id = self._button(method, action_id)
        return self.Binding.with_user(user).action_decide_approval(
            self.MODEL, (record or self.record).id, method, action_id, approve
        )

    def _withdraw(self, user, row, record=None):
        return self.Binding.with_user(user).action_withdraw_decision(
            self.MODEL, (record or self.record).id, self.METHOD, False, row.id
        )

    def _row(self, request, user):
        return request.approver_ids.filtered(lambda a: a.user_id == user)


@tagged("post_install", "-at_install", "mail_activity")
class TestStudioApproval(StudioApprovalCase):
    def test_00_constraints(self):
        step = self._step()
        binding = self._request(step).binding_id or self.Binding.search(
            [("category_id", "=", step.category_id.id)]
        )
        with self.assertRaises(ValidationError, msg="no binding on a missing method"):
            binding.method = "atomize"
        self._decide(self.manager)
        with self.assertRaises(UserError, msg="one decision per user and record"):
            self._decide(self.manager)
        with self.assertRaises(UserError):
            binding.method = "open_commercial_entity"
        with self.assertRaises(UserError):
            binding.model_id = self.env.ref("base.model_res_partner_bank_account")
        with self.assertRaises(UserError, msg="a step holding decisions is archived"):
            step.unlink()

    def test_01_single_rule(self):
        self._step()
        with self.assertRaises(UserError, msg="outside the pool, no decision"):
            self._decide(self.user)
        self.assertFalse(self._check(self.user))
        self._decide(self.manager)
        self.assertTrue(self._check(self.user))

    def test_02_single_rule_on_action(self):
        action = self.env.ref("base.action_partner_form")
        self._step(action_id=action.id)
        with self.assertRaises(UserError):
            self._decide(self.user, action_id=action.id)
        self.assertFalse(self._check(self.user, action_id=action.id))
        self._decide(self.manager, action_id=action.id)
        self.assertTrue(self._check(self.user, action_id=action.id))

    def test_03_single_rule_with_domain(self):
        self._step(subject_domain="[('is_company', '=', True)]")
        company = self.env.ref("base.main_company").partner_id
        self.assertFalse(self._check(self.user, company))
        self.assertTrue(self._check(self.user, self.record), "no step applies")

    def test_04_rule_rejection(self):
        step = self._step()
        self._decide(self.manager, approve=False)
        self.assertFalse(self._check(self.user))
        self.assertFalse(self._check(self.manager), "not even the refuser proceeds")
        request = self._request(step)
        refusal = request.approver_ids.filtered(lambda a: a.state == "refused")
        self._withdraw(self.manager, refusal)
        self._decide(self.manager)
        self.assertTrue(self._check(self.user))

    def test_05_different_users(self):
        base = self._step(group_id=self.group_user.id, name="Base")
        self._step(exclusive=True, sequence=1, name="Exclusive")
        self.assertFalse(self._check(self.user), "the user decides the base step only")
        self._withdraw(self.user, self._row(self._request(base), self.user))
        self.assertFalse(self._check(self.manager), "one exclusive approval")
        [spec] = self.Binding.with_user(self.manager).get_button_approvals(
            [
                {
                    "model": self.MODEL,
                    "res_id": self.record.id,
                    "method": self.METHOD,
                    "action_id": False,
                }
            ]
        )
        by_manager = [
            decision
            for step in spec["steps"]
            for decision in step["decisions"]
            if decision["user_id"] == self.manager.id
        ]
        self.assertEqual(len(by_manager), 1)
        self.assertTrue(self._check(self.user))

    def test_06_security(self):
        base = self._step(group_id=self.group_user.id, name="User step")
        self._step(exclusive=True, sequence=1, name="Manager step")
        self._decide(self.user)
        self._decide(self.manager)
        request = self._request(base)
        with self.assertRaises(AccessError, msg="not someone else's decision"):
            self._withdraw(self.manager, self._row(request, self.user))
        with self.assertRaises(UserError, msg="no second decision"):
            self._decide(self.manager)
        with self.assertRaises(AccessError, msg="not someone else's decision"):
            self._withdraw(self.user, self._row(request, self.manager))

    def test_07_forbidden_record(self):
        model, method = "res.company", "action_all_company_branches"
        main_company = self.manager.company_id
        alternate = self.env["res.company"].create({"name": "SomeCompany"})
        step = self.Step.browse(
            self.Binding.create_step_for_button(model, method, False)
        )
        step.group_id = self.group_manager

        def spec(company):
            return self.Binding.with_user(self.manager).get_button_approvals(
                [
                    {
                        "model": model,
                        "res_id": company.id,
                        "method": method,
                        "action_id": False,
                    }
                ]
            )

        self.assertTrue(spec(main_company)[0]["gated"])
        with self.assertRaises(AccessError, msg="no spec on a record I cannot read"):
            spec(alternate)
        with self.assertRaises(
            AccessError, msg="no decision on a record I cannot write"
        ):
            self.Binding.with_user(self.manager).action_decide_approval(
                model, main_company.id, method, False, True
            )

    def test_08_archive(self):
        self._step(group_id=self.group_user.id, name="User step")
        exclusive = self._step(exclusive=True, sequence=1, name="Manager step")
        self.assertFalse(self._check(self.manager))
        exclusive.active = False
        self.assertTrue(
            self.Binding.with_context(active_test=False)
            .with_user(self.manager)
            .check_button_approval(self.MODEL, self.record.id, self.METHOD, False)[
                "approved"
            ]
        )

    def test_09_archive_reverse(self):
        base = self._step(group_id=self.group_user.id, name="User step")
        self._step(exclusive=True, sequence=1, name="Manager step")
        self._decide(self.manager)
        base.active = False
        self.assertTrue(self._check(self.manager))

    def test_10_exclusive_collision(self):
        self._step(group_id=self.group_user.id, name="User step")
        self._step(exclusive=True, sequence=1, group_id=self.group_user.id)
        self._step(
            method="open_commercial_entity", exclusive=True, group_id=self.group_user.id
        )
        self.assertFalse(self._check(self.user))
        self.assertTrue(self._check(self.user, method="open_commercial_entity"))

    def _asked(self, step, user):
        return self._request(step).activity_ids.filtered(lambda a: a.user_id == user)

    def test_11_approval_activity(self):
        step = self._step(user_ids=[Command.set(self.manager.ids)])
        self._check(self.user)
        activity = self._asked(step, self.manager)
        self.assertEqual(len(activity), 1)
        activity.with_user(self.manager).action_done()
        self.assertTrue(self._check(self.user))
        self.assertFalse(activity.active)

    def test_12_approval_activity_spoof(self):
        step = self._step(user_ids=[Command.set(self.manager.ids)])
        self._check(self.user)
        activity = self._asked(step, self.manager)
        activity.with_user(self.user).action_done()
        self.assertFalse(
            self._check(self.user), "marking it done as someone else decides nothing"
        )
        self.assertFalse(activity.active)

    def test_13_approval_activity_dismissal(self):
        step = self._step(user_ids=[Command.set(self.manager.ids)])
        self._check(self.user)
        activity = self._asked(step, self.manager)
        self._decide(self.manager)
        self.assertFalse(activity.exists() and activity.active)

    def test_14_approval_activity_dismissal_refused(self):
        step = self._step(user_ids=[Command.set(self.manager.ids)])
        self._check(self.user)
        activity = self._asked(step, self.manager)
        self._decide(self.manager, approve=False)
        self.assertFalse(activity.exists() and activity.active)

    def test_15_approval_notification_order(self):
        first = self._step(user_ids=[Command.set(self.manager.ids)], name="First")
        self._step(user_ids=[Command.set(self.user.ids)], group_id=False, name="Second")
        outsider = mail_new_test_user(
            self.env,
            login="Outsider",
            groups="base.group_user,base.group_partner_manager",
        )
        self._check(outsider)
        request = self._request(first)
        self.assertEqual(
            request.activity_ids.user_id, self.manager, "the first step only"
        )
        self._decide(self.manager)
        self.assertEqual(request.activity_ids.user_id, self.user, "then the second")

    def test_16_batched_approval_spec(self):
        self._step(user_ids=[Command.set(self.manager.ids)])
        self._step(
            method="open_commercial_entity", name="You didn't say the magic word 2!"
        )
        specs = self.Binding.with_user(self.user).get_button_approvals(
            [
                {
                    "model": self.MODEL,
                    "res_id": self.record.id,
                    "method": method,
                    "action_id": False,
                }
                for method in (self.METHOD, "open_commercial_entity")
            ]
        )
        self.assertEqual(len(specs), 2)
        self.assertEqual(specs[0]["steps"][0]["name"], "You didn't say the magic word!")
        self.assertEqual(
            specs[1]["steps"][0]["name"], "You didn't say the magic word 2!"
        )


@tagged("post_install", "-at_install")
class TestStudioApprovalPost(StudioApprovalCase):
    def test_approval_method_patch(self):
        partners = self.env["res.partner"].with_user(self.user).search([], limit=2)
        partner, other = partners[0], partners[1]
        partner_class = self.env.registry["res.partner"]
        self.assertFalse(
            hasattr(partner_class.open_commercial_entity, "approval_binding_origin")
        )
        origin_result = partner.with_user(self.user).open_commercial_entity()
        step = self._step(method="open_commercial_entity")
        self.assertTrue(
            hasattr(partner_class.open_commercial_entity, "approval_binding_origin")
        )
        user_result = partner.with_user(self.user).open_commercial_entity()
        self.assertEqual(user_result["res_model"], "approval.request", "asked, not run")
        manager_result = partner.with_user(self.manager).open_commercial_entity()
        self.assertDictEqual(
            manager_result, origin_result, "the manager approves and runs it"
        )
        step.active = False
        other_result = other.with_user(self.user).open_commercial_entity()
        self.assertEqual(
            other_result["res_model"], "res.partner", "no step left, nothing asked"
        )

    def test_approval_method_patch_sudo(self):
        partner = self.env["res.partner"].with_user(self.user).search([], limit=1)
        self._step(method="open_commercial_entity")
        result = partner.with_user(self.user).sudo().open_commercial_entity()
        self.assertEqual(result["res_model"], "approval.request")

    def test_approval_methods_protection(self):
        for method in ("_fields_sync", "__setattr__", "create", "write", "unlink"):
            with self.subTest(method=method), self.assertRaises(ValidationError):
                self.Binding.create_step_for_button(self.MODEL, method, False)
