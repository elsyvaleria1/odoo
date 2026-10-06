from odoo import models
from odoo.tools import frozendict


class SurveyQuestion(models.Model):
    _inherit = "survey.question"

    _access_anchors = frozendict(
        {
            "owner": "survey_id.restrict_user_ids",
            "survey_appraisal_manager_user": models.Anchor(
                "survey_id.appraisal_manager_user_ids", kind="owner"
            ),
        }
    )


class SurveyUserInputLine(models.Model):
    _inherit = "survey.user_input.line"

    _access_anchors = frozendict(
        {
            "owner": models.Anchor("survey_id.restrict_user_ids", shared=True),
            "user_input_appraisal_manager_user": models.Anchor(
                "user_input_id.appraisal_id.manager_ids.user_id", kind="owner"
            ),
        }
    )
