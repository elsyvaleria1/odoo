from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.base.models.ir_actions_server import ServerActionWithWarningsError
from odoo.addons.base.tests.test_ir_actions import TestServerActionsBase
from odoo.addons.test_automation.tests.test_flow import create_automation


class TestServerActionsValidation(TestServerActionsBase):
    def test_multi_action_children_warnings(self):
        self.action.write({"state": "multi", "child_ids": [self.test_server_action.id]})
        self.assertEqual(self.action.model_id.model, "res.partner")
        self.assertEqual(self.test_server_action.model_id.model, "ir.actions.server")
        self.assertEqual(
            self.action.warning,
            "Following child actions should have the same model (Contact): TestDummyServerAction",
        )

        new_action = self.action.copy()
        with self.assertRaises(ValidationError) as ve:
            new_action.write({"child_ids": [self.action.id]})
        self.assertEqual(
            ve.exception.args[0], "Following child actions have warnings: TestAction"
        )

    def test_webhook_payload_includes_group_restricted_fields(self):
        self.test_server_action.write(
            {
                "state": "webhook",
                "webhook_field_ids": [
                    self.env["ir.model.fields"]._get("ir.actions.server", "code").id
                ],
            }
        )
        self.assertEqual(
            self.test_server_action.warning,
            "Group-restricted fields cannot be included in "
            "webhook payloads, as it could allow any user to "
            "accidentally leak sensitive information. You will "
            "have to remove the following fields from the webhook payload:\n"
            "- Python Code",
        )

    def test_recursion_in_child(self):
        new_action = self.action.copy()
        self.action.write({"state": "multi", "child_ids": [new_action.id]})
        with self.assertRaises(ValidationError) as ve:
            new_action.write({"child_ids": [self.action.id]})
        self.assertEqual(
            ve.exception.args[0], "Recursion found in child server actions"
        )

    def test_non_relational_field_traversal(self):
        self.action.write(
            {
                "state": "object_write",
                "update_path": "parent_id.name",
                "value": "TestNew",
            }
        )
        with self.assertRaises(ValidationError) as ve:
            self.action.write({"update_path": "parent_id.name.something_else"})
        message = ve.exception.args[0]
        self.assertIn("Field to Update Path", message)
        self.assertIn("non-relational", message)
        self.assertIn("Name", message)

    def test_python_bad_expr(self):
        with self.assertRaises(ValidationError) as ve:
            self.test_server_action.write({"code": "this is invalid python code"})
        self.assertEqual(
            ve.exception.args[0],
            "SyntaxError : invalid syntax at line 1\nthis is invalid python code\n",
        )

    def test_cannot_run_if_warnings(self):
        self.action.write({"state": "multi", "child_ids": [self.test_server_action.id]})
        self.assertTrue(self.action.warning)
        with self.assertRaises(ServerActionWithWarningsError) as e:
            self.action.run()
        self.assertEqual(
            e.exception.args[0],
            "Server action TestAction has one or more warnings, address them first.",
        )


class TestOnUnlinkWarnsForActionsNeedingTheirRecord(TestServerActionsBase):

    def _configured(self, state, model):
        values = {"name": f"Act {state}", "model_id": model.id, "state": state}
        if state in ("object_create", "object_copy"):
            values["link_field_id"] = (
                self.env["ir.model.fields"]._get("mail.test.lead", "message_ids").id
            )
        return self.env["ir.actions.server"].create(values)

    def test_every_state_that_needs_its_record_warns_on_unlink(self):
        Action = self.env["ir.actions.server"]
        states = Action._get_states_needing_a_live_record()
        self.assertIn("remove_followers", states, "the omission that started this")
        self.assertIn("sms", states, "sms renders a template against the record too")

        model = self.env["ir.model"]._get("mail.test.lead")
        for state in sorted(states):
            with self.subTest(state=state):
                action = self._configured(state, model)
                rule = self.env["automation.rule"].new(
                    {
                        "name": "On delete",
                        "model_id": model.id,
                        "trigger": "on_unlink",
                        "action_server_ids": [(6, 0, action.ids)],
                    }
                )
                result = rule._onchange_trigger_or_actions()
                self.assertTrue(
                    result and result.get("warning"),
                    f"an `on_unlink` rule running a {state!r} action must warn",
                )

    def test_a_state_that_survives_its_record_does_not_warn(self):
        model = self.env["ir.model"]._get("mail.test.lead")
        action = self.env["ir.actions.server"].create(
            {"name": "Log it", "model_id": model.id, "state": "code", "code": "pass"}
        )
        rule = self.env["automation.rule"].new(
            {
                "name": "On delete",
                "model_id": model.id,
                "trigger": "on_unlink",
                "action_server_ids": [(6, 0, action.ids)],
            }
        )
        self.assertFalse(rule._onchange_trigger_or_actions())

    def test_a_create_with_nothing_to_link_to_survives_its_record(self):
        model = self.env["ir.model"]._get("mail.test.lead")
        action = self.env["ir.actions.server"].create(
            {
                "name": "Make one",
                "model_id": model.id,
                "state": "object_create",
                "value": "spawned",
            }
        )
        self.assertFalse(action.link_field_id, "precondition: nothing to link to")
        self.assertIn("object_create", action._get_states_needing_a_live_record())
        self.assertFalse(action._is_live_record_required())

        rule = self.env["automation.rule"].new(
            {
                "name": "On delete",
                "model_id": model.id,
                "trigger": "on_unlink",
                "action_server_ids": [(6, 0, action.ids)],
            }
        )
        self.assertFalse(rule._onchange_trigger_or_actions())

    def test_the_warning_names_the_actions_it_found(self):
        model = self.env["ir.model"]._get("mail.test.lead")
        action = self._configured("object_write", model)
        rule = self.env["automation.rule"].new(
            {
                "name": "On delete",
                "model_id": model.id,
                "trigger": "on_unlink",
                "action_server_ids": [(6, 0, action.ids)],
            }
        )
        message = rule._onchange_trigger_or_actions()["warning"]["message"]
        self.assertIn(action.name, message)
        self.assertNotIn("send an email", message)


@tagged("post_install", "-at_install")
class TestAutomationBatchesWhatItCan(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.lead_model = cls.env["ir.model"]._get("mail.test.lead")

    def _spy_on(self, method_name):
        seen = []
        cls = type(self.env["ir.actions.server"])
        origin = getattr(cls, method_name)

        def spy(action, eval_context=None):
            seen.append(len(action._get_records_targeted()))
            return origin(action, eval_context=eval_context)

        self.patch(cls, method_name, spy)
        return seen

    def test_a_mail_action_runs_once_for_the_whole_batch(self):
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger="on_write",
            _actions={
                "state": "followers",
                "followers_type": "generic",
                "followers_partner_field_name": "partner_id",
            },
        )
        seen = self._spy_on("_run_action_followers_multi")

        partner = self.env["res.partner"].create({"name": "Cust"})
        leads = self.env["mail.test.lead"].create(
            [{"name": f"L{i}", "partner_id": partner.id} for i in range(5)]
        )
        leads.write({"name": "touched"})

        self.assertEqual(
            set(seen),
            {5},
            "every entry holds the whole write, never one record of it",
        )
        self.assertLess(
            len(seen),
            5,
            "and there are fewer entries than records -- measured [5] against "
            "[1, 1, 1, 1, 1] in a plain process; a rule created inside the test "
            "transaction re-registers the hooks and so is entered twice, which "
            "is why the count is bounded rather than pinned",
        )
        for lead in leads:
            self.assertIn(partner, lead.message_partner_ids, "and it did the work")

    def test_a_code_action_still_runs_once_per_record(self):
        automation = create_automation(
            self,
            model_id=self.lead_model.id,
            trigger="on_write",
            _actions={
                "state": "code",
                "code": "record.write({'customer_name': (record.customer_name or '') + 'x'})",
            },
        )
        self.assertFalse(automation.action_server_ids._is_batchable())
        seen = self._spy_on("_run_action_code_multi")

        leads = self.env["mail.test.lead"].create([{"name": f"C{i}"} for i in range(4)])
        leads.write({"name": "touched"})
        self.assertEqual(set(seen), {1}, "one record per entry, as before")
        self.assertGreaterEqual(len(seen), 4, "and every record got its own")
        for lead in leads:
            self.assertEqual(
                lead.customer_name,
                "x",
                "every record was reached, not just the first",
            )


@tagged("post_install", "-at_install")
class TestAvailableModelsNeverWiden(TransactionCase):

    def test_no_state_offers_a_model_base_would_not(self):
        Action = self.env["ir.actions.server"]
        allowed = {
            name for name in self.env.registry if self.env[name].has_access("read")
        }
        model = self.env["ir.model"]._get("mail.test.lead")

        for state, _label in Action._fields["state"].selection:
            with self.subTest(state=state):
                action = Action.new({"model_id": model.id, "state": state})
                offered = action.available_model_ids.mapped("model")
                self.assertFalse(
                    [name for name in offered if name not in allowed],
                    f"a {state!r} action offers models base excluded",
                )


@tagged("post_install", "-at_install")
class TestMultiActionTakesTheBatchWhenItsChildrenCan(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.lead_model = cls.env["ir.model"]._get("mail.test.lead")
        cls.follower = cls.env["res.partner"].create({"name": "Follower"})

    def _child(self, **values):
        if values.get("state") in ("followers", "remove_followers"):
            values.setdefault("followers_type", "specific")
            values.setdefault("partner_ids", [(6, 0, self.follower.ids)])
        return self.env["ir.actions.server"].create(
            {"name": "Child", "model_id": self.lead_model.id, **values}
        )

    def _multi_over(self, children):
        return self.env["ir.actions.server"].create(
            {
                "name": "Both",
                "model_id": self.lead_model.id,
                "state": "multi",
                "child_ids": [(6, 0, children.ids)],
            }
        )

    def test_all_children_batchable(self):
        children = self._child(state="followers") | self._child(
            state="remove_followers"
        )
        self.assertTrue(self._multi_over(children)._is_batchable())

    def test_one_child_that_cannot(self):
        children = self._child(
            state="followers", followers_type="specific"
        ) | self._child(state="code", code="pass")
        self.assertFalse(
            self._multi_over(children)._is_batchable(),
            "one `code` child means the whole thing runs per record",
        )

    def test_a_multi_of_multis(self):
        inner = self._multi_over(
            self._child(state="followers", followers_type="specific")
        )
        self.assertTrue(self._multi_over(inner)._is_batchable())


@tagged("post_install", "-at_install")
class TestConfigurationIsSeededNotImposed(TransactionCase):

    def test_no_compute_reimposes_its_default_over_a_chosen_value(self):
        Action = self.env["ir.actions.server"]
        model = self.env["ir.model"]._get("automation.lead.thread.test")
        candidates = [
            field
            for field in Action._fields.values()
            if field.type == "selection"
            and field.store
            and field.compute
            and not field.readonly
            and field.name != "state"
        ]
        self.assertTrue(candidates, "the contract needs something to measure")

        for state, _label in Action._fields["state"].selection:
            try:
                with self.env.cr.savepoint():
                    action = Action.create(
                        {"name": f"Act {state}", "model_id": model.id, "state": state}
                    )
            except ValidationError:
                continue
            for field in candidates:
                seeded = action[field.name]
                if not seeded:
                    continue
                options = [
                    value for value, __ in field._description_selection(self.env)
                ]
                chosen = next((value for value in options if value != seeded), None)
                if chosen is None:
                    continue
                with self.subTest(state=state, field=field.name):
                    action[field.name] = chosen
                    action.write({"state": state})
                    self.assertEqual(
                        action[field.name],
                        chosen,
                        f"writing `state` with the value it already had put "
                        f"{field.name} back to {seeded!r}; seed a default when "
                        f"the field is empty, do not assign it every pass",
                    )
