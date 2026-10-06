from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from .test_typed_steps import TypedStepCase


@tagged("post_install", "-at_install")
class TestActsOn(TypedStepCase):
    def _join(self, **reconcile_vals):
        register = self._typed_step("workflow_register_statement", name="Register")
        invoice = self._document_step(name="Invoice")
        reconcile = self._typed_step(
            "workflow_reconcile_statement",
            name="Reconcile",
            predecessors=register | invoice,
            **reconcile_vals,
        )
        return register, invoice, reconcile

    def _settle(self, runtime, first, second, reconcile, st_line):
        self._line(runtime, first).action_run()
        self._line(runtime, second).action_run()
        with patch.object(
            type(st_line),
            "set_line_bank_statement_line",
            autospec=True,
        ) as reconciled:
            self._line(runtime, reconcile).action_run()
        return reconciled

    def test_a_join_that_names_no_document_is_a_problem(self):
        self._join()

        problems = self.automation._get_step_reference_problems()

        self.assertEqual(len(problems), 1)
        self.assertRegex(problems[0], "'Register', 'Invoice'|'Invoice', 'Register'")
        self.assertIn("Acts On", problems[0])

    def test_such_a_join_starts_no_run(self):
        self._join()

        with self.assertRaisesRegex(UserError, "cannot start or update a run"):
            self._make_runtime(st_line_id=self._statement_line().id)

    def test_the_named_document_is_settled_whichever_branch_ran_first(self):
        register, invoice, reconcile = self._join()
        reconcile.workflow_source_step_id = invoice
        self.assertFalse(self.automation._get_step_reference_problems())

        for first, second in ((register, invoice), (invoice, register)):
            with self.subTest(first=first.name):
                st_line = self._statement_line()
                runtime = self._make_runtime(st_line_id=st_line.id)
                self.assertEqual(
                    runtime.line_ids.filtered(lambda line: line.state == "ready"),
                    self._line(runtime, register) | self._line(runtime, invoice),
                )

                reconciled = self._settle(runtime, first, second, reconcile, st_line)

                move = self._line(runtime, invoice).created_record_ref
                receivable = move.line_ids.filtered(
                    lambda line: line.account_id.account_type == "asset_receivable",
                )
                reconciled.assert_called_once_with(st_line, receivable.ids)
                self.assertEqual(runtime.state, "done")

    def test_acts_on_must_name_a_step_upstream(self):
        invoice = self._document_step(name="Invoice")
        reconcile = self._typed_step("workflow_reconcile_statement", name="Reconcile")
        reconcile.workflow_source_step_id = invoice

        problems = self.automation._get_step_reference_problems()

        self.assertRegex(problems[0], "'Invoice'.*not upstream")

    def test_acts_on_must_name_a_step_that_makes_a_document(self):
        invoice = self._document_step(name="Invoice")
        first = self._typed_step(
            "workflow_reconcile_statement", name="First", predecessors=invoice
        )
        second = self._typed_step(
            "workflow_reconcile_statement", name="Second", predecessors=first
        )
        second.workflow_source_step_id = first

        problems = self.automation._get_step_reference_problems()

        self.assertRegex(problems[0], "'First', which makes none")

    def test_a_step_named_in_acts_on_cannot_be_removed(self):
        _register, invoice, reconcile = self._join()
        reconcile.workflow_source_step_id = invoice

        with self.assertRaisesRegex(Exception, "Reconcile"):
            invoice.unlink()

    def test_a_chain_still_needs_no_acts_on(self):
        register = self._typed_step("workflow_register_statement", name="Register")
        invoice = self._document_step(name="Invoice", predecessors=register)
        self._typed_step(
            "workflow_reconcile_statement", name="Reconcile", predecessors=invoice
        )

        self.assertFalse(self.automation._get_step_reference_problems())

    def test_a_code_step_reads_the_documents_by_key(self):
        invoice = self._document_step(name="Invoice")
        reader = self._typed_step(
            "code",
            name="Reader",
            predecessors=invoice,
            code="record._set_output({'amount': steps.invoice.record.amount_total})",
        )
        runtime = self._make_runtime()

        runtime.action_run_all()

        self.assertEqual(self._line(runtime, reader).output, {"amount": 100.0})
