from odoo import fields
from odoo.fields import Command
from odoo.tests.common import tagged

from .common import AutomationAccountCommon


@tagged("post_install", "-at_install")
class TestPredecessorWalks(AutomationAccountCommon):
    def setUp(self):
        super().setUp()
        self.step = self._make_step("pass")
        self.runtime = self._make_runtime()

    def _make_line(self, name, created_record=None, predecessors=None):
        vals = {
            "runtime_id": self.runtime.id,
            "name": name,
            "action_id": self.step.id,
        }
        if created_record is not None:
            vals["created_record_ref"] = f"{created_record._name},{created_record.id}"
        line = self.env["automation.runtime.line"].create(vals)
        if predecessors is not None:
            self._link_lines(predecessors, line)
        return line

    def _make_move(self, ref):
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
                "journal_id": self.journal_sale.id,
                "invoice_date": "2026-08-20",
                "ref": ref,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": ref,
                            "quantity": 1,
                            "price_unit": 100.0,
                            "account_id": self.account_income.id,
                            "tax_ids": [],
                        },
                    ),
                ],
            },
        )
        move.action_post()
        return move

    def test_a_cycle_returns_instead_of_recursing(self):
        first = self._make_line("cycle a")
        second = self._make_line("cycle b")
        self._link_lines(second, first)
        self._link_lines(first, second)

        self.assertFalse(first._get_nearest_move())
        self.assertFalse(first._get_nearest_payment())
        self.assertFalse(first._get_nearest_document_date())

    def test_a_diamond_visits_each_ancestor_once(self):
        root = self._make_line("root")
        previous = root
        lines = root
        for index in range(6):
            left = self._make_line(f"left {index}", predecessors=previous)
            right = self._make_line(f"right {index}", predecessors=previous)
            join = self._make_line(f"join {index}", predecessors=left | right)
            lines |= left | right | join
            previous = join

        visits = []
        original = type(root)._get_nearest_move

        def counted(record, visited=None):
            visits.append(record.id)
            return original(record, visited)

        self.patch(type(root), "_get_nearest_move", counted)

        self.assertFalse(previous._get_nearest_move())
        self.assertEqual(len(visits), len(lines))
        self.assertEqual(len(set(visits)), len(visits))

    def test_the_walk_still_finds_a_move_through_a_chain(self):
        move = self._make_move("chain source")
        source = self._make_line("with move", created_record=move)
        middle = self._make_line("middle", predecessors=source)
        sink = self._make_line("sink", predecessors=middle)

        self.assertEqual(sink._get_nearest_move(), move)

    def test_the_document_date_walk_still_reaches_a_predecessor(self):
        move = self._make_move("date source")
        source = self._make_line("with move", created_record=move)
        sink = self._make_line("sink", predecessors=source)

        self.assertEqual(sink._get_nearest_document_date(), move.invoice_date)

    def test_a_statement_line_date_beats_a_predecessor_move(self):
        statement_line = self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.journal_bank.id,
                "payment_ref": "WALK-STLINE",
                "partner_id": self.partner.id,
                "amount": -100.0,
                "date": "2026-01-05",
            },
        )
        self.runtime.st_line_id = statement_line

        move = self._make_move("later than the statement")
        source = self._make_line("with move", created_record=move)
        sink = self._make_line("sink", predecessors=source)

        self.assertEqual(move.invoice_date, fields.Date.to_date("2026-08-20"))
        self.assertEqual(
            sink._get_nearest_document_date(),
            fields.Date.to_date("2026-01-05"),
        )
