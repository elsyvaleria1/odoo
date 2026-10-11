from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPlanningFieldServiceSearch(TransactionCase):

    def _search_arch(self, xmlid, model):
        return self.env[model].get_view(self.env.ref(xmlid).id, "search")["arch"]

    def test_the_analysis_report_search_stays_valid(self):
        report_search = self.env.ref("planning.planning_analysis_report_view_search")
        report_search._check_xml()
        arch = self._search_arch(
            "planning.planning_analysis_report_view_search",
            "planning.analysis.report",
        )
        self.assertNotIn('name="partner_id"', arch)
        self.assertIn('name="in_progress_filter"', arch)

    def test_the_shift_searches_offer_the_customer(self):
        for xmlid in (
            "planning.planning_view_search",
            "planning_field_service.planning_slot_view_search_visit",
        ):
            with self.subTest(view=xmlid):
                arch = self._search_arch(xmlid, "planning.slot")
                self.assertIn('name="partner_id"', arch)
                self.assertIn('name="partner_city"', arch)
                self.assertIn('name="group_by_customer"', arch)
