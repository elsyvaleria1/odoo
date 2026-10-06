from contextlib import ExitStack
from unittest.mock import patch

from odoo.tests import TransactionCase

from odoo.addons.account_edi_ubl_cii.tools.ubl_line import update_ubl_discount_node


class TestUblLineAllowances(TransactionCase):
    def test_discount_suppression_preserves_amount_code_and_other_nodes(self):
        amount = {"_text": "12.00", "currencyID": "EUR"}
        code = {"_text": "95"}
        node = {"cbc:Amount": amount, "cbc:AllowanceChargeReasonCode": code}
        self.assertIsNone(update_ubl_discount_node(node))
        self.assertIs(node["cbc:Amount"], amount)
        self.assertIs(node["cbc:AllowanceChargeReasonCode"], code)
        for key in (
            "cbc:AllowanceChargeReason",
            "cbc:MultiplierFactorNumeric",
            "cbc:BaseAmount",
        ):
            self.assertIn(key, node)
            self.assertIsNone(node[key])

    def test_country_and_order_discount_hooks(self):
        currency = self.env.ref("base.EUR")
        values = {
            "currency": currency,
            "amount": 12,
            "base_amount": 120,
            "percent": 10,
            "is_charge": False,
        }
        for model in (
            "account.edi.xml.ubl_a_nz",
            "account.edi.xml.ubl_sg",
            "account.edi.xml.ubl_de",
            "trade.edi.xml.ubl_bis3",
        ):
            with self.subTest(model=model):
                node = self.env[model]._ubl_get_line_allowance_charge_discount_node(
                    {}, values
                )
                self.assertEqual(str(node["cbc:Amount"]["_text"]), "12.00")
                self.assertEqual(node["cbc:Amount"]["currencyID"], "EUR")
                self.assertEqual(node["cbc:AllowanceChargeReasonCode"], {"_text": "95"})
                self.assertIsNone(node["cbc:AllowanceChargeReason"])
                self.assertIsNone(node["cbc:MultiplierFactorNumeric"])
                self.assertIsNone(node["cbc:BaseAmount"])

    def test_allowance_dispatch_preserves_order_and_shared_context(self):
        steps = (
            "_ubl_add_line_allowance_charge_nodes",
            "_ubl_add_line_allowance_charge_nodes_for_discount",
            "_ubl_add_line_allowance_charge_nodes_for_recycling_contribution_taxes",
            "_ubl_add_line_allowance_charge_nodes_for_excise_taxes",
        )
        for model, hook in (
            ("account.edi.xml.ubl_bis3", "_add_invoice_line_allowance_charge_nodes"),
            ("trade.edi.xml.ubl_bis3", "_add_order_line_allowance_charge_nodes"),
        ):
            exporter = self.env[model]
            node, base_line, original_line_vals = {}, {}, {"old": True}
            vals = {"base_line": base_line, "line_vals": original_line_vals}
            with self.subTest(model=model), ExitStack() as stack:
                calls = []

                def record_step(name, calls=calls):
                    def record(step_context):
                        calls.append((name, step_context))
                        step_context["line_node"][name] = True

                    return record

                for step in steps:
                    stack.enter_context(
                        patch.object(
                            type(exporter), step, side_effect=record_step(step)
                        )
                    )
                self.assertIsNone(getattr(exporter, hook)(node, vals))
                self.assertEqual([name for name, _ in calls], list(steps))
                context = calls[0][1]
                self.assertTrue(all(value is context for _, value in calls))
                self.assertIsNot(context, vals)
                self.assertIs(context["line_node"], node)
                self.assertIs(context["line_vals"]["base_line"], base_line)
                self.assertIs(vals["line_vals"], original_line_vals)
                self.assertEqual(list(node), list(steps))

    def test_missing_base_line_does_not_mutate_node(self):
        for model, hook in (
            ("account.edi.xml.ubl_bis3", "_add_invoice_line_allowance_charge_nodes"),
            ("trade.edi.xml.ubl_bis3", "_add_order_line_allowance_charge_nodes"),
        ):
            node = {"existing": True}
            with self.subTest(model=model), self.assertRaises(KeyError):
                getattr(self.env[model], hook)(node, {})
            self.assertEqual(node, {"existing": True})
