from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPlanningAnalysisReport(TransactionCase):
    def test_the_report_names_every_status_a_shift_can_have(self):
        self.assertEqual(
            self.env["planning.analysis.report"].fields_get(["state"], ["selection"]),
            {
                "state": {
                    "selection": self.env["planning.slot"]
                    ._fields["state"]
                    ._description_selection(self.env)
                }
            },
        )
