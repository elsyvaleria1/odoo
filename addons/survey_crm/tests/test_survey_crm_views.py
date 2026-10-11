from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSurveyCrmViews(TransactionCase):
    def test_the_lead_indicator_is_a_known_button(self):
        view = self.env.ref("survey_crm.survey_survey_view_form")
        with self.assertNoLogs("odoo.addons.base.models.ir_ui_view", "WARNING"):
            view._check_xml()
