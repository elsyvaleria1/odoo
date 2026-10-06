from datetime import timedelta

from odoo.tests import tagged

from odoo.addons.account_collection.tests.common import CollectionCommon


@tagged("post_install", "-at_install")
class TestCustodyReport(CollectionCommon):
    def _report(self, user=None):
        report = self.env["account.collection.custody.report"]
        if user:
            report = report.with_user(user)
        return report.search([("company_id", "=", self.env.company.id)])

    def test_custody_is_read_by_how_long_it_has_been_held(self):
        fresh = self._collect(self._post_invoice(100.0), 100.0)
        held = self._collect(
            self._post_invoice(200.0), 200.0, date=self.today - timedelta(days=2)
        )
        old = self._collect(
            self._post_invoice(300.0), 300.0, date=self.today - timedelta(days=10)
        )

        rows = {row.payment_id: row for row in self._report()}

        self.assertEqual(rows[fresh].age, "0_1")
        self.assertEqual(rows[held].age, "2_3")
        self.assertEqual(rows[old].age, "4_plus")
        self.assertEqual(rows[old].age_days, 10)
        self.assertEqual(rows[old].amount, 300.0)
        self.assertEqual(rows[old].collector_id, self.collector)
        self.assertTrue(rows[old].is_overdue)
        self.assertFalse(rows[fresh].is_overdue)

    def test_a_collector_reads_only_their_own_custody(self):
        own = self._collect(self._post_invoice(100.0), 100.0)
        other = self._collect(
            self._post_invoice(200.0), 200.0, collector=self.other_collector
        )

        self.assertEqual(self._report(self.collector).payment_id, own)
        self.assertEqual(self._report(self.treasurer).payment_id, own | other)

    def test_a_handed_in_collection_leaves_the_report(self):
        payment = self._collect(self._post_invoice(100.0), 100.0)
        remittance = (
            self.env["account.collection.remittance"]
            .with_user(self.collector)
            .create({"destination_journal_id": self.till_journal.id})
        )
        remittance.action_load_custody()
        remittance.action_submit()
        remittance.with_user(self.treasurer).action_validate()

        self.assertNotIn(payment, self._report().payment_id)
