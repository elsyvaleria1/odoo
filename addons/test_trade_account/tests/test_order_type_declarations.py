from odoo.tests import TransactionCase, tagged

from odoo.addons.trade.tools import TradeDirection, direction_of

ORDER_MODELS = ["sale.order", "purchase.order", "test_trade.order"]
ORDER_LINE_MODELS = ["sale.order.line", "purchase.order.line", "test_trade.order.line"]

ORDER_DECLARATIONS = [
    "_sequence_code",
    "_lock_setting_field",
    "_mark_sent_context_key",
    "_display_name_context_key",
    "_portal_url_prefix",
]


@tagged("post_install", "-at_install")
class TestOrderTypeDeclarations(TransactionCase):

    def test_every_order_model_declares_what_the_mixin_reads(self):
        for model_name in ORDER_MODELS:
            model = self.env[model_name]
            for attribute in ORDER_DECLARATIONS:
                with self.subTest(model=model_name, attribute=attribute):
                    self.assertTrue(
                        getattr(model, attribute, ""),
                        f"{model_name} does not declare {attribute}",
                    )

    def test_every_order_and_line_model_declares_its_direction(self):
        for model_name in ORDER_MODELS + ORDER_LINE_MODELS:
            with self.subTest(model=model_name):
                self.assertIsInstance(self.env[model_name]._direction, TradeDirection)

    def test_an_order_and_its_lines_trade_the_same_way(self):
        for order_name, line_name in zip(ORDER_MODELS, ORDER_LINE_MODELS, strict=True):
            with self.subTest(order=order_name):
                self.assertEqual(
                    direction_of(self.env[order_name]).key,
                    direction_of(self.env[line_name]).key,
                )

    def test_a_model_that_declares_no_direction_is_refused(self):
        order = self.env["test_trade.order"]
        direction = order.__class__._direction
        order.__class__._direction = None
        try:
            with self.assertRaises(NotImplementedError):
                order._get_order_type()
        finally:
            order.__class__._direction = direction

    def test_no_two_order_models_share_a_sequence_code(self):
        codes = [self.env[name]._sequence_code for name in ORDER_MODELS]

        self.assertEqual(
            len(codes),
            len(set(codes)),
            f"order models share a sequence code: {codes}",
        )

    def test_each_order_model_draws_names_from_its_own_sequence(self):
        for model_name in ORDER_MODELS:
            model = self.env[model_name]
            sequence = (
                self.env["ir.sequence"]
                .sudo()
                .search([("code", "=", model._sequence_code)], limit=1)
            )
            order = model.create({"partner_id": self.env.user.partner_id.id})
            with self.subTest(model=model_name):
                self.assertTrue(sequence, f"no sequence for {model._sequence_code}")
                self.assertNotEqual(order.name, "New")
                self.assertTrue(
                    order.name.startswith(sequence.prefix),
                    f"{model_name} was named {order.name!r}, which does not come "
                    f"from its own sequence (prefix {sequence.prefix!r})",
                )

    def test_sequence_codes_resolve_to_exactly_one_sequence(self):
        for model_name in ORDER_MODELS:
            code = self.env[model_name]._sequence_code
            with self.subTest(model=model_name, code=code):
                sequences = self.env["ir.sequence"].sudo().search([("code", "=", code)])
                self.assertEqual(
                    len(sequences),
                    1,
                    f"{code} resolves to {len(sequences)} sequences: "
                    f"{sequences.mapped('prefix')}",
                )

    def test_every_order_sequence_is_global(self):
        for model_name in ORDER_MODELS:
            code = self.env[model_name]._sequence_code
            sequences = self.env["ir.sequence"].sudo().search([("code", "=", code)])
            with self.subTest(model=model_name, code=code):
                self.assertTrue(sequences)
                self.assertFalse(
                    sequences.company_id,
                    f"{code} is scoped to {sequences.company_id.mapped('name')}, "
                    f"so it shadows any global sequence of the same code and "
                    f"leaves other companies unnamed",
                )

    def test_an_order_created_in_a_second_company_is_still_named(self):
        second = self.env["res.company"].create({"name": "Second Co"})
        self.env.user.company_ids = [(4, second.id)]
        partner = self.env["res.partner"].create({"name": "Second Co Partner"})

        order = (
            self.env["test_trade.order"]
            .with_company(second)
            .create({"partner_id": partner.id, "company_id": second.id})
        )

        self.assertNotEqual(order.name, "New")
        self.assertTrue(order.name)
