import logging
import unittest

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import TestPoSCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestPosConfigSettingsView(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config

    def test_settings_keeps_updates_to_linked_records(self):
        note = self.env["pos.note"].create({"name": "Before"})
        self.config.note_ids = note
        values = {
            "note_ids": [
                Command.link(note.id),
                Command.update(note.id, {"name": "After"}),
            ],
        }

        changed = self.config.with_context(
            from_settings_view=True
        )._prepare_vals_changed(values)
        self.assertEqual(
            note.name, "Before", "comparison must not write related records"
        )
        self.assertEqual(changed, values)

        self.config.with_context(from_settings_view=True).write(values)

        note.invalidate_recordset()
        self.assertEqual(note.name, "After")
        self.assertEqual(self.config.note_ids, note)

    def test_settings_update_preserves_payment_method_membership(self):
        methods = self.config.payment_method_ids
        method = methods[:1]
        self.config.with_context(from_settings_view=True).write(
            {
                "payment_method_ids": [
                    Command.update(method.id, {"name": "Updated in settings"})
                ],
            }
        )
        _logger.debug(
            "Settings update methods before=%s after=%s",
            methods.ids,
            self.config.payment_method_ids.ids,
        )
        self.assertEqual(self.config.payment_method_ids, methods)
        self.assertEqual(method.name, "Updated in settings")

    def test_settings_unlink_preserves_other_payment_methods(self):
        methods = self.config.payment_method_ids
        self.assertGreater(len(methods), 1)
        self.config.with_context(from_settings_view=True).write(
            {
                "payment_method_ids": [Command.unlink(methods[0].id)],
            }
        )
        _logger.debug(
            "Settings unlink methods before=%s after=%s",
            methods.ids,
            self.config.payment_method_ids.ids,
        )
        self.assertEqual(self.config.payment_method_ids, methods[1:])


@tagged("post_install", "-at_install")
class TestPosConfigOpenSessionGuard(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config

    def test_open_sessions_prevent_archiving(self):
        self.env["pos.session"].create({"config_id": self.config.id})
        with self.assertRaises(UserError):
            self.config.active = False

        self.config.write({"name": "Editable while open", "active": True})
        self.assertEqual(self.config.name, "Editable while open")

    def test_reordered_settings_links_are_not_a_payment_method_change(self):
        self.env["pos.session"].create({"config_id": self.config.id})
        methods = self.config.payment_method_ids
        self.assertGreater(len(methods), 1)

        self.config.with_context(from_settings_view=True).write(
            {
                "payment_method_ids": [
                    Command.link(method.id) for method in reversed(methods)
                ],
            }
        )

        self.assertEqual(set(self.config.payment_method_ids.ids), set(methods.ids))

    def test_forbidden_settings_update_does_not_write_before_rejection(self):
        self.env["pos.session"].create({"config_id": self.config.id})
        method = self.config.payment_method_ids[0]
        original_name = method.name
        values = {
            "payment_method_ids": [
                Command.link(pm.id) for pm in self.config.payment_method_ids
            ]
            + [Command.update(method.id, {"name": "Must never be written"})]
        }

        # Avoid TransactionCase.assertRaises' savepoint: rollback could hide an early write.
        with unittest.TestCase.assertRaises(self, UserError):
            self.config.with_context(from_settings_view=True).write(values)

        method.invalidate_recordset()
        self.assertEqual(method.name, original_name)

    def test_session_guard_rejects_a_batch_with_one_open_config(self):
        second = self.config.copy({"name": "Closed config"})
        self.env["pos.session"].create({"config_id": self.config.id})
        with self.assertRaises(UserError):
            (second | self.config).write({"active": False})
        self.assertTrue(second.active)
        self.assertTrue(self.config.active)

    def test_session_guard_costs_no_query_for_unrestricted_keys(self):
        self.env["pos.session"].create({"config_id": self.config.id})
        with self.assertQueryCount(0):
            self.config._check_session_forbidden_changes({"name": "Rename"})
        with self.assertRaises(UserError):
            self.config._check_session_forbidden_changes({"active": False})

    def test_payment_bypass_does_not_bypass_archiving(self):
        method = self.bank_pm1.copy({"name": "Extra bank"})
        self.env["pos.session"].create({"config_id": self.config.id})
        config = self.config.with_context(
            bypass_payment_method_ids_forbidden_change=True
        )
        config.write({"payment_method_ids": [Command.link(method.id)]})
        self.assertIn(method, config.payment_method_ids)
        with self.assertRaises(UserError):
            config.action_archive()

    def test_a_pos_manager_may_rename_but_not_archive_an_open_config(self):
        manager = self.env["res.users"].create(
            {
                "name": "Challenge POS manager",
                "login": "config_challenge_manager",
                "company_id": self.config.company_id.id,
                "company_ids": [Command.set(self.config.company_id.ids)],
                "group_ids": [
                    Command.set(
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("point_of_sale.group_pos_manager").id,
                        ]
                    )
                ],
            }
        )
        self.env["pos.session"].create({"config_id": self.config.id})
        config = self.config.with_user(manager)
        config.write({"name": "Manager rename"})
        self.assertEqual(config.name, "Manager rename")
        with self.assertRaises(UserError):
            config.action_archive()


@tagged("post_install", "-at_install")
class TestPosConfigFieldConsistency(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config

    def test_payment_journal_change_refreshes_cash_control(self):
        method = self.env["pos.payment.method"].create(
            {
                "name": "Initially on account",
                "company_id": self.config.company_id.id,
            }
        )
        self.config.payment_method_ids = [Command.set(method.ids)]
        self.assertFalse(self.config.cash_control)

        method.journal_id = self.cash_pm1.journal_id

        self.assertTrue(self.config.cash_control)

    def test_fiscal_positions_are_not_discarded_by_an_unrelated_write(self):
        position = self.env["account.fiscal.position"].create(
            {"name": "Audit FP", "company_id": self.env.company.id}
        )
        self.config.write(
            {
                "tax_regime_selection": True,
                "fiscal_position_ids": [(6, 0, position.ids)],
            }
        )
        self.config.write({"receipt_footer": "unrelated"})
        self.assertEqual(self.config.fiscal_position_ids, position)

    def test_fiscal_positions_can_be_set_without_touching_the_regime_flag(self):
        position = self.env["account.fiscal.position"].create(
            {"name": "Audit FP 2", "company_id": self.env.company.id}
        )
        config = self.config.copy({"name": "fp-target"})
        config.write({"fiscal_position_ids": [(6, 0, position.ids)]})
        self.assertEqual(config.fiscal_position_ids, position)

    def test_turning_the_tax_regime_off_clears_the_fiscal_positions(self):
        position = self.env["account.fiscal.position"].create(
            {"name": "Audit FP 3", "company_id": self.env.company.id}
        )
        self.config.write(
            {
                "tax_regime_selection": True,
                "fiscal_position_ids": [(6, 0, position.ids)],
            }
        )
        self.config.write({"tax_regime_selection": False})
        self.assertFalse(self.config.fiscal_position_ids)

    def test_emptying_the_fast_payment_list_turns_the_feature_off(self):
        methods = self.config.payment_method_ids
        self.config.write(
            {
                "use_fast_payment": True,
                "fast_payment_method_ids": [(6, 0, methods.ids[:1])],
            }
        )
        self.config.write({"payment_method_ids": [(3, methods.ids[0])]})
        self.assertFalse(self.config.use_fast_payment)

    def test_fast_payment_without_a_fast_method_is_refused(self):
        methods = self.config.payment_method_ids
        self.config.write(
            {
                "use_fast_payment": True,
                "fast_payment_method_ids": [(6, 0, methods.ids[:1])],
            }
        )
        with self.assertRaises(ValidationError):
            self.config.write(
                {
                    "use_fast_payment": True,
                    "payment_method_ids": [(3, methods.ids[0])],
                }
            )
