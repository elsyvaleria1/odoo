from odoo import api, fields, models
from odoo.tools import frozendict


class SurveySurvey(models.Model):
    _inherit = "survey.survey"
    _access_anchors = frozendict(
        {
            "appraisal_manager_user": models.Anchor(
                "appraisal_manager_user_ids", kind="owner"
            ),
            "owner": "restrict_user_ids",
        }
    )

    survey_type = fields.Selection(
        selection_add=[("appraisal", "Appraisal")],
        ondelete={"appraisal": "set default"},
    )
    appraisal_manager_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="survey_survey_res_users_appraisal_rel",
        string="Appraisals Managers Users",
        compute="_compute_appraisal_manager_user_ids",
        store=True,
        readonly=True,
        help="Users allowed to view the survey used in an appraisal",
    )

    @api.onchange("survey_type")
    def _onchange_survey_type(self) -> None:
        super()._onchange_survey_type()
        if self.survey_type == "appraisal":
            self.write(
                {
                    "access_mode": "token",
                    "is_attempts_limited": True,
                    "users_can_go_back": True,
                }
            )

    @api.depends("survey_type")
    @api.depends_context("uid")
    def _compute_allowed_survey_types(self) -> None:
        super()._compute_allowed_survey_types()
        if self.env.user.has_group(
            "hr_appraisal.group_hr_appraisal_user"
        ) or self.env.user.has_group("survey.group_survey_user"):
            for survey in self:
                survey.allowed_survey_types = (survey.allowed_survey_types or []) + [
                    "appraisal"
                ]

    @api.depends(
        "survey_type",
        "user_input_ids",
        "user_input_ids.appraisal_id",
        "user_input_ids.appraisal_id.manager_ids",
    )
    def _compute_appraisal_manager_user_ids(self) -> None:
        appraisal_surveys = self.filtered(
            lambda s: s.survey_type == "appraisal" and s.user_input_ids
        )
        (self - appraisal_surveys).appraisal_manager_user_ids = False
        for survey in appraisal_surveys:
            survey.appraisal_manager_user_ids = (
                survey.user_input_ids.appraisal_id.manager_ids.user_id
            )

    def action_survey_user_input_completed(self):
        action = super().action_survey_user_input_completed()
        if self.survey_type == "appraisal":
            action.update({"domain": [("survey_id.survey_type", "=", "appraisal")]})
        return action

    def action_survey_user_input(self):
        action = super().action_survey_user_input()
        if self.survey_type == "appraisal":
            action.update({"domain": [("survey_id.survey_type", "=", "appraisal")]})
        return action

    def get_formview_id(self, access_uid=None):
        self.check_singleton()
        if self.survey_type == "appraisal":
            access_user = (
                self.env["res.users"].browse(access_uid)
                if access_uid
                else self.env.user
            )
            if not access_user.has_group("survey.group_survey_user"):
                if view := self.env.ref(
                    "hr_appraisal_survey.survey_survey_view_form",
                    raise_if_not_found=False,
                ):
                    return view.id
        return super().get_formview_id(access_uid=access_uid)
