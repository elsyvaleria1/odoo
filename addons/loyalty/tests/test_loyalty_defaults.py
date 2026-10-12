from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLoyaltyDefaults(TransactionCase):
    def test_child_default_values_reads_the_create_command(self):
        Program = self.env["loyalty.program"]
        defaults = Program._program_type_default_values()

        rule_defaults = Program._get_child_default_values("gift_card", "rule_ids")
        self.assertEqual(rule_defaults, defaults["gift_card"]["rule_ids"][1][2])

        reward_defaults = Program._get_child_default_values("buy_x_get_y", "reward_ids")
        self.assertEqual(reward_defaults["reward_type"], "product")

    def test_child_default_values_of_a_type_that_contributes_none(self):
        Program = self.env["loyalty.program"]

        self.assertEqual(Program._get_child_default_values("coupons", "rule_ids"), {})
        self.assertEqual(
            Program._get_child_default_values("promotion", "communication_plan_ids"), {}
        )
        self.assertEqual(
            Program._get_child_default_values("not_a_program_type", "rule_ids"), {}
        )

    def test_rule_default_get_follows_the_program_type(self):
        rule_defaults = (
            self.env["loyalty.rule"]
            .with_context(program_type="buy_x_get_y")
            .default_get(["reward_point_mode", "minimum_qty"])
        )

        self.assertEqual(rule_defaults["reward_point_mode"], "unit")
        self.assertEqual(rule_defaults["minimum_qty"], 2)

    def test_reward_default_get_follows_the_program_type(self):
        reward_defaults = (
            self.env["loyalty.reward"]
            .with_context(program_type="gift_card")
            .default_get(["reward_type", "discount_mode", "discount_applicability"])
        )

        self.assertEqual(reward_defaults["discount_mode"], "per_point")
        self.assertEqual(reward_defaults["discount_applicability"], "order")

    def test_default_get_asks_only_for_the_requested_fields(self):
        reward_defaults = (
            self.env["loyalty.reward"]
            .with_context(program_type="gift_card")
            .default_get(["discount_mode"])
        )

        self.assertEqual(
            set(reward_defaults) & {"discount_applicability", "required_points"}, set()
        )
