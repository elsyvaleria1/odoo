
from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLoyaltyProgramWrite(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.programs = cls.env["loyalty.program"].create(
            [
                {"name": "Batch A", "reward_ids": [Command.create({})]},
                {"name": "Batch B", "reward_ids": [Command.create({})]},
            ]
        )

    def test_program_type_change_on_a_batch(self):
        self.env.flush_all()
        self.programs.write({"program_type": "coupons"})
        self.env.flush_all()

        self.assertEqual(set(self.programs.mapped("program_type")), {"coupons"})
        for program in self.programs:
            self.assertTrue(program.reward_ids, "each program keeps a reward")

    def test_deferred_program_type_recompute_on_a_batch(self):
        self.env.flush_all()
        self.programs.program_type = "promo_code"
        self.env.flush_all()

        self.assertEqual(set(self.programs.mapped("program_type")), {"promo_code"})

    def test_a_batch_of_code_programs_gets_a_code_each(self):
        programs = self.env["loyalty.program"].create(
            [
                {"name": "Coded A"},
                {"name": "Coded B"},
            ]
        )
        self.env.flush_all()
        programs.write({"program_type": "promo_code"})
        self.env.flush_all()

        codes = programs.rule_ids.mapped("code")
        self.assertEqual(len(codes), 2)
        self.assertTrue(all(codes), "each rule carries a code")
        self.assertEqual(len(set(codes)), 2, "and the two differ")

    def test_switching_a_batch_to_a_coded_type(self):
        self.env.flush_all()
        self.programs.write({"program_type": "promo_code"})
        self.env.flush_all()

        codes = self.programs.rule_ids.mapped("code")
        self.assertEqual(len(set(codes)), 2)

    def test_a_rule_switched_to_with_code_gets_one(self):
        program = self.env["loyalty.program"].create({"name": "Auto rule"})
        self.env.flush_all()
        self.assertEqual(program.program_type, "promotion")
        self.assertFalse(program.rule_ids.code)

        program.rule_ids.mode = "with_code"

        self.assertTrue(program.rule_ids.code)

    def test_an_explicit_code_is_kept(self):
        program = self.env["loyalty.program"].create(
            {
                "name": "Explicit",
                "program_type": "promo_code",
                "rule_ids": [Command.create({"code": "KEEPME", "minimum_amount": 0})],
                "reward_ids": [Command.create({})],
            }
        )
        self.env.flush_all()

        self.assertEqual(program.rule_ids.code, "KEEPME")

    def test_writing_reward_ids_on_a_batch(self):
        self.programs.write({"reward_ids": [Command.create({"discount": 5})]})

        for program in self.programs:
            self.assertEqual(len(program.reward_ids), 2)

    def test_clearing_the_rewards_of_a_batch_is_still_refused(self):
        with self.assertRaises(ValidationError):
            self.programs.write({"reward_ids": [Command.clear()]})
            self.env.flush_all()

    def test_commands_leave_a_reward(self):
        leaves = self.env["loyalty.program"]._commands_leave_a_reward
        self.assertTrue(
            leaves([Command.clear(), Command.create({})]), "cleared then recreated"
        )
        self.assertTrue(leaves([Command.set([1, 2])]), "set to two rewards")
        self.assertTrue(leaves([Command.link(1)]))
        self.assertTrue(leaves([{"discount": 5}]), "a bare dict of values")
        self.assertFalse(leaves([Command.clear()]), "cleared and not refilled")
        self.assertFalse(leaves([Command.set([])]), "set to nothing")
        self.assertFalse(
            leaves([Command.clear(), Command.create({}), Command.unlink(1)])
        )
        self.assertFalse(leaves([]), "no command at all")
        self.assertFalse(
            leaves([Command.unlink(1)]),
            "an unknown starting count answers False, so the constraint runs",
        )
        self.assertFalse(
            leaves([Command.update(1, {"discount": 5})]),
            "an update creates no reward, so the constraint runs",
        )
