from odoo.tests import TransactionCase

from odoo.addons.account_edi_ubl_cii.models.account_edi_common import FloatFmt
from odoo.addons.account_edi_ubl_cii.tools.ubl_line import update_ubl_line_price_node


class TestUblLinePrice(TransactionCase):
    def test_price_precision_and_currency(self):
        for value, text in (
            (0, "0.0"),
            (1, "1.0"),
            (-12.5, "-12.5"),
            (1.2345678, "1.234568"),
        ):
            with self.subTest(value=value):
                node = {}
                vals = {
                    "base_line": {"_ubl_values": {"price_amount_currency": value}},
                    "currency_name": "CHF",
                }
                self.assertIsNone(update_ubl_line_price_node(node, vals))
                amount = node["cac:Price"]["cbc:PriceAmount"]
                self.assertIsInstance(amount["_text"], FloatFmt)
                self.assertEqual(str(amount["_text"]), text)
                self.assertEqual(amount["currencyID"], "CHF")

    def test_replaces_price_without_changing_other_nodes_or_input(self):
        old_price = {"old": "price"}
        other = {"_text": "unchanged"}
        node = {"cac:Price": old_price, "cbc:ID": other}
        base_line = {"_ubl_values": {"price_amount_currency": 12.5}}
        vals = {"base_line": base_line, "currency_name": "EUR"}
        update_ubl_line_price_node(node, vals)
        self.assertIs(node["cbc:ID"], other)
        self.assertEqual(old_price, {"old": "price"})
        self.assertIs(vals["base_line"], base_line)
        self.assertEqual(
            vals,
            {
                "base_line": {"_ubl_values": {"price_amount_currency": 12.5}},
                "currency_name": "EUR",
            },
        )
        self.assertNotIn("old", node["cac:Price"])

    def test_invalid_inputs_leave_existing_price_untouched(self):
        for vals, error in (
            ({}, KeyError),
            ({"base_line": {}}, KeyError),
            ({"base_line": {"_ubl_values": {}}}, KeyError),
            ({"base_line": {"_ubl_values": {"price_amount_currency": 1}}}, KeyError),
            (
                {
                    "base_line": {"_ubl_values": {"price_amount_currency": "invalid"}},
                    "currency_name": "EUR",
                },
                ValueError,
            ),
        ):
            price = {"old": "price"}
            node = {"cac:Price": price}
            with self.subTest(vals=vals), self.assertRaises(error):
                update_ubl_line_price_node(node, vals)
            self.assertIs(node["cac:Price"], price)

    def test_invoice_and_order_hooks_use_the_same_price_contract(self):
        for model, method in (
            ("account.edi.xml.ubl_bis3", "_add_invoice_line_price_nodes"),
            ("trade.edi.xml.ubl_bis3", "_add_order_line_price_nodes"),
        ):
            node = {}
            vals = {
                "base_line": {"_ubl_values": {"price_amount_currency": 3.125}},
                "currency_name": "USD",
            }
            with self.subTest(model=model):
                self.assertIsNone(getattr(self.env[model], method)(node, vals))
                amount = node["cac:Price"]["cbc:PriceAmount"]
                self.assertEqual(str(amount["_text"]), "3.125")
                self.assertEqual(amount["currencyID"], "USD")
