from odoo.http import Controller, request, route
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SurveyAnalyzeResultsRoute(Controller):
    @route(
        '/survey/<model("survey.survey"):survey>/analyze-results',
        methods=["POST"],
        type="http",
        auth="user",
    )
    def survey_analyze_results(self, survey):
        action = survey.action_survey_open_linked_spreadsheet()
        spreadsheet_id = action.get("params", {}).get("spreadsheet_id")
        _debug.lifecycle(
            "survey_results_analyzed", survey=survey, spreadsheet_id=spreadsheet_id
        )
        return request.redirect(
            f"/odoo/surveys/{survey.id}/spreadsheet/{spreadsheet_id}"
        )
