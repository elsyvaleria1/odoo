from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.approval.tests.common import ApprovalCommon, add_category_approver


@tagged("post_install", "-at_install")
class TestApprovalBindingIntegrity(ApprovalCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Binding = cls.env["approval.binding"]
        cls.partner_model = cls.env["ir.model"]._get("res.partner")
        cls.caller = cls._partner_user("integrity_caller")
        cls.decider = cls._partner_user("integrity_decider")
        cls.category = cls.env["approval.category"].create(
            {"name": "Integrity Category", "approval_minimum": 1}
        )
        add_category_approver(cls.category, cls.decider, required=True, sequence=10)

    @classmethod
    def _partner_user(cls, login, **vals):
        return cls.env["res.users"].create(
            {
                "name": login,
                "login": login,
                "email": f"{login}@test.com",
                "group_ids": [
                    (4, cls.env.ref("base.group_user").id),
                    (4, cls.env.ref("base.group_partner_manager").id),
                ],
                **vals,
            }
        )

    def tearDown(self):
        self.Binding._unregister_hook()
        super().tearDown()

    def _bind(self, **vals):
        binding = self.Binding.create(
            {
                "model_id": self.partner_model.id,
                "method": "action_archive",
                "category_id": self.category.id,
                **vals,
            }
        )
        self.Binding._unregister_hook()
        self.Binding._register_hook()
        return binding

    def _partner(self, **vals):
        return self.env["res.partner"].create({"name": "Integrity Partner", **vals})

    def _requests_for(self, binding, partner):
        return self.env["approval.request"].search(
            [
                ("binding_id", "=", binding.id),
                ("res_model", "=", "res.partner"),
                ("res_id", "=", partner.id),
            ]
        )

    def _approve(self, request, user=None, **context):
        user = user or self.decider
        request.approver_ids.filtered(lambda row: row.user_id == user).with_user(
            user
        ).with_context(**context).action_approve()

    def _approved_request_for(self, partner, binding=False):
        request = self.env["approval.request"].create(
            {
                "name": "Approved elsewhere",
                "category_id": self.category.id,
                "request_owner_id": self.caller.id,
                "res_model": "res.partner",
                "res_id": partner.id,
                "binding_id": binding and binding.id,
            }
        )
        request.action_confirm()
        self._approve(request)
        self.assertEqual(request.state, "approved")
        return request

    # -- coverage is the binding's own ---------------------------------------

    def test_an_approval_the_binding_did_not_raise_does_not_cover_the_record(self):
        self._bind(mode="block")
        partner = self._partner()
        self._approved_request_for(partner)
        with self.assertRaises(UserError):
            partner.with_user(self.caller).action_archive()
        self.assertTrue(partner.active)

    def test_an_approval_another_binding_raised_does_not_cover_the_record(self):
        self._bind(mode="block")
        other = self._bind(mode="block", method="action_unarchive")
        partner = self._partner()
        self._approved_request_for(partner, other)
        with self.assertRaises(UserError):
            partner.with_user(self.caller).action_archive()
        self.assertTrue(partner.active)

    def test_an_approval_the_binding_raised_covers_the_record(self):
        binding = self._bind(mode="block")
        partner = self._partner()
        self._approved_request_for(partner, binding)
        partner.with_user(self.caller).action_archive()
        self.assertFalse(partner.active)

    # -- the condition reads what the caller cannot ------------------------

    def test_a_condition_through_a_record_the_caller_cannot_read_still_selects(self):
        hidden_company = self.env["res.company"].create({"name": "Integrity Hidden"})
        parent = self._partner(name="Secret parent", company_id=hidden_company.id)
        child = self._partner(
            name="Child", company_id=False, parent_id=parent.id, type="other"
        )
        self._bind(
            mode="block", subject_domain="[('parent_id.name', '=', 'Secret parent')]"
        )
        as_caller = child.with_user(self.caller).with_context(
            allowed_company_ids=[self.env.company.id]
        )
        with self.assertRaises(UserError):
            as_caller.action_archive()
        self.assertTrue(child.active)

    # -- what may be bound, and by whom --------------------------------------

    def test_no_approval_engine_model_can_be_bound_even_by_the_superuser(self):
        for model in ("approval.category", "approval.request"):
            with self.subTest(model=model), self.assertRaises(ValidationError):
                self.Binding.create(
                    {
                        "model_id": self.env["ir.model"]._get(model).id,
                        "method": "action_archive",
                    }
                )

    def _system_model_binding_vals(self):
        return {
            "model_id": self.env["ir.model"]._get("ir.cron").id,
            "method": "method_direct_trigger",
        }

    def test_an_approval_manager_cannot_bind_a_system_model(self):
        with self.assertRaises(ValidationError):
            self.Binding.with_user(self.manager_user).create(
                self._system_model_binding_vals()
            )

    def test_an_approval_manager_cannot_make_a_gate_apply_to_the_superuser(self):
        with self.assertRaises(ValidationError):
            self.Binding.with_user(self.manager_user).create(
                {
                    "model_id": self.partner_model.id,
                    "method": "action_archive",
                    "mode": "block",
                    "category_id": self.category.id,
                    "sudo_policy": "enforce",
                }
            )
        binding = self.Binding.with_user(self.manager_user).create(
            {
                "model_id": self.partner_model.id,
                "method": "action_archive",
                "mode": "block",
                "category_id": self.category.id,
            }
        )
        with self.assertRaises(ValidationError):
            binding.write({"sudo_policy": "enforce"})

    def test_a_system_administrator_may_bind_a_system_model_and_enforce(self):
        admin = self.env["res.users"].create(
            {
                "name": "Integrity Admin",
                "login": "integrity_admin",
                "email": "integrity_admin@test.com",
                "group_ids": [
                    (4, self.env.ref("base.group_system").id),
                    (4, self.env.ref("approval.group_approval_manager").id),
                ],
            }
        )
        Binding = self.Binding.with_user(admin)
        self.assertTrue(Binding.create(self._system_model_binding_vals()).exists())
        enforced = Binding.create(
            {
                "model_id": self.partner_model.id,
                "method": "action_archive",
                "mode": "block",
                "category_id": self.category.id,
                "sudo_policy": "enforce",
            }
        )
        self.assertEqual(enforced.sudo_policy, "enforce")

    # -- the replay acts in the owner's companies ----------------------------

    def test_the_replay_runs_in_the_owners_companies_not_the_approvers_session(self):
        home = self.env.company
        elsewhere = self.env["res.company"].create({"name": "Integrity Elsewhere"})
        owner = self._partner_user(
            "integrity_owner", company_id=home.id, company_ids=[(6, 0, home.ids)]
        )
        approver = self._partner_user(
            "integrity_far_approver",
            company_id=elsewhere.id,
            company_ids=[(6, 0, (home | elsewhere).ids)],
        )
        category = self.env["approval.category"].create(
            {"name": "Integrity Far", "approval_minimum": 1}
        )
        add_category_approver(category, approver, required=True, sequence=10)
        binding = self._bind(
            mode="request", category_id=category.id, run_on_approval=True
        )
        partner = self._partner(company_id=False)
        partner.with_user(owner).with_context(
            allowed_company_ids=home.ids
        ).action_archive()
        request = self._requests_for(binding, partner)
        self.assertEqual(request.state, "pending")
        self._approve(request, approver, allowed_company_ids=(elsewhere | home).ids)
        self.assertEqual(request.state, "approved")
        self.assertFalse(request.binding_replay_error)
        self.assertTrue(request.date_binding_replayed)
        self.assertFalse(partner.active)
        self.assertEqual(partner.write_uid, owner)

    # -- a call the replay could not repeat ----------------------------------

    def _subscribe_binding(self, run_on_approval):
        return self._bind(
            mode="request",
            method="message_subscribe",
            run_on_approval=run_on_approval,
        )

    def test_a_call_with_arguments_is_refused_when_approval_would_replay_it(self):
        binding = self._subscribe_binding(run_on_approval=True)
        partner = self._partner()
        follower = self._partner(name="Integrity Follower")
        with self.assertRaises(UserError):
            partner.with_user(self.caller).message_subscribe(partner_ids=follower.ids)
        self.assertFalse(self._requests_for(binding, partner))
        self.assertNotIn(follower, partner.message_partner_ids)

    def test_a_call_with_arguments_asks_when_approval_leaves_it_to_the_caller(self):
        binding = self._subscribe_binding(run_on_approval=False)
        partner = self._partner()
        follower = self._partner(name="Integrity Follower")
        action = partner.with_user(self.caller).message_subscribe(
            partner_ids=follower.ids
        )
        request = self._requests_for(binding, partner)
        self.assertEqual(request.state, "pending")
        self.assertEqual(action["res_id"], request.id)
        self.assertNotIn(follower, partner.message_partner_ids)

    # -- the kill switch reaches the button ------------------------------------

    def test_the_kill_switch_lets_the_button_through_without_a_request(self):
        binding = self._bind(mode="request", run_on_approval=False)
        partner = self._partner()
        self.env["ir.config_parameter"].set_param("approval.binding_enabled", "False")
        Binding = self.Binding.with_user(self.caller)
        check = Binding.check_button_approval(
            "res.partner", partner.id, "action_archive", False
        )
        self.assertEqual(check, {"approved": True, "request_id": False})
        self.assertFalse(self._requests_for(binding, partner))
        (spec,) = Binding.get_button_approvals(
            [{"model": "res.partner", "res_id": partner.id, "method": "action_archive"}]
        )
        self.assertFalse(spec["gated"])
        self.assertTrue(spec["approved"])

    # -- a check is not a run -----------------------------------------------

    def test_approving_from_the_button_check_does_not_count_as_the_run(self):
        category = self.env["approval.category"].create(
            {
                "name": "Integrity Self",
                "approval_minimum": 1,
                "allow_self_approval": True,
            }
        )
        add_category_approver(category, self.caller, required=False, sequence=10)
        binding = self._bind(
            mode="request",
            category_id=category.id,
            approve_on_invoke=True,
            run_on_approval=True,
        )
        partner = self._partner()
        check = self.Binding.with_user(self.caller).check_button_approval(
            "res.partner", partner.id, "action_archive", False
        )
        self.assertTrue(check["approved"])
        request = self._requests_for(binding, partner)
        self.assertEqual(request.state, "approved")
        self.assertTrue(partner.active)
        self.assertFalse(request.date_binding_replayed)
        row = request.approver_ids.filtered(lambda row: row.user_id == self.caller)
        request.with_user(self.caller).action_withdraw_approver(row.id)
        self.assertEqual(request.state, "pending")
        row.with_user(self.caller).action_approve()
        self.assertEqual(request.state, "approved")
        self.assertFalse(partner.active, "the operation never ran, so approval runs it")
        self.assertTrue(request.date_binding_replayed)
        self.assertFalse(request.binding_replay_error)

    def test_an_operation_the_button_ran_is_not_run_again_on_reapproval(self):
        category = self.env["approval.category"].create(
            {
                "name": "Integrity Once",
                "approval_minimum": 1,
                "allow_self_approval": True,
            }
        )
        add_category_approver(category, self.caller, required=False, sequence=10)
        binding = self._bind(
            mode="request",
            category_id=category.id,
            approve_on_invoke=True,
            run_on_approval=True,
        )
        partner = self._partner()
        self.Binding.with_user(self.caller).check_button_approval(
            "res.partner", partner.id, "action_archive", False
        )
        partner.with_user(self.caller).action_archive()
        self.assertFalse(partner.active)
        request = self._requests_for(binding, partner)
        self.assertTrue(request.date_binding_replayed, "the covered call is the run")
        partner.action_unarchive()
        row = request.approver_ids.filtered(lambda row: row.user_id == self.caller)
        request.with_user(self.caller).action_withdraw_approver(row.id)
        row.with_user(self.caller).action_approve()
        self.assertEqual(request.state, "approved")
        self.assertTrue(partner.active, "re-approval does not run it a second time")

    # -- a method with no records --------------------------------------------

    def test_a_method_that_runs_on_the_model_cannot_be_bound(self):
        with self.assertRaises(ValidationError):
            self.Binding.create(
                {
                    "model_id": self.partner_model.id,
                    "method": "get_or_create",
                    "mode": "advise",
                }
            )

    def test_the_wrapper_keeps_what_the_api_decorators_stamped_on_the_method(self):
        binding = self._bind(mode="advise", category_id=False)
        self.env.cr.execute(
            "UPDATE approval_binding SET method = 'get_or_create' WHERE id = %s",
            [binding.id],
        )
        binding.invalidate_recordset(["method"])
        self.env.registry.clear_cache()
        self.Binding._unregister_hook()
        self.Binding._register_hook()
        wrapper = self.env.registry["res.partner"].get_or_create
        self.assertTrue(hasattr(wrapper, "approval_binding_origin"))
        self.assertTrue(getattr(wrapper, "_api_model", False))
        self.assertEqual(wrapper.__name__, "get_or_create")

    # -- the editor adopts the button's own binding ----------------------------

    def _assert_adopted_by_the_editor(self, binding):
        step = self.env["approval.category.step"].browse(
            self.Binding.create_step_for_button("res.partner", "action_archive", False)
        )
        self.assertEqual(
            self.Binding.with_context(active_test=False).search(
                [("model_name", "=", "res.partner"), ("method", "=", "action_archive")]
            ),
            binding,
        )
        self.assertTrue(binding.active)
        self.assertEqual(
            (binding.mode, binding.approve_on_invoke, binding.run_on_approval),
            ("request", True, False),
        )
        self.assertTrue(binding.category_id)
        self.assertEqual(step.category_id, binding.category_id)

    def test_the_editor_adopts_a_button_binding_that_only_observed(self):
        binding = self._bind(mode="advise", category_id=False)
        self._assert_adopted_by_the_editor(binding)

    def test_the_editor_adopts_an_archived_button_binding(self):
        binding = self._bind(
            mode="request", approve_on_invoke=True, run_on_approval=False
        )
        binding.active = False
        self._assert_adopted_by_the_editor(binding)
