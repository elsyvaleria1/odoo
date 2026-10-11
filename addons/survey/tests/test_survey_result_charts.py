from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestSurveyResultCharts(HttpCase):
    def test_the_trend_chart_draws_without_a_global_chart(self):
        survey = self.env["survey.survey"].create(
            {"title": "Chart probe", "access_mode": "public"}
        )
        self.env["survey.user_input"].create(
            [{"survey_id": survey.id, "state": "done"} for _ in range(2)]
        )
        canvas = "document.querySelector('.o_survey_trend_canvas')"
        self.browser_js(
            f"/survey/results/{survey.id}",
            """
            if (window.Chart) {
                console.error("a global Chart is still published");
            } else {
                console.log("test successful");
            }
            """,
            f"{canvas} && {canvas}.style.boxSizing === 'border-box'",
            login="admin",
        )
