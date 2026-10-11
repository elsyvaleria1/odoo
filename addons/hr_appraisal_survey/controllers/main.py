from odoo import http
from odoo.exceptions import AccessDenied
from odoo.fields import Domain
from odoo.http import request

from odoo.addons.survey.controllers.main import Survey


class AppraisalSurvey(Survey):
    def _check_validity(
        self,
        survey_sudo,
        answer_sudo,
        answer_token,
        ensure_token=True,
        check_partner=True,
    ):
        validity_code = super()._check_validity(
            survey_sudo, answer_sudo, answer_token, ensure_token, check_partner
        )

        if (
            validity_code == "answer_wrong_user"
            and survey_sudo.survey_type == "appraisal"
            and answer_sudo
            and check_partner
        ):
            user_employees = request.env["hr.employee"].search(
                [("user_id", "=", request.env.user.id)]
            )
            partners = user_employees.partner_id | request.env.user.partner_id
            if not request.env.user._is_public() and answer_sudo.partner_id in partners:
                return True
        return validity_code

    def _get_access_data(
        self, survey_token, answer_token, ensure_token=True, check_partner=True
    ):
        access_data = super()._get_access_data(
            survey_token, answer_token, ensure_token, check_partner
        )
        survey_sudo = access_data["survey_sudo"]
        answer_sudo = access_data["answer_sudo"]

        if (
            survey_sudo
            and answer_sudo
            and survey_sudo.survey_type == "appraisal"
            and access_data.get("validity_code", False) == "answer_deadline"
        ):
            appraisal = answer_sudo.appraisal_id
            user = request.env.user
            if user in appraisal.manager_ids.mapped("user_id") or user.has_group(
                "hr_appraisal.group_hr_appraisal_user"
            ):
                access_data["can_answer"] = False
                access_data["validity_code"] = True
        return access_data

    @staticmethod
    def _get_id_param(post, name):
        value = post.get(name)
        if isinstance(value, bool):
            return 0
        if isinstance(value, int):
            return max(0, value)
        if isinstance(value, str) and value.isdecimal():
            return int(value)
        return 0

    @staticmethod
    def _appraisal_results_role(appraisal):
        user = request.env.user
        if (
            user.has_group("hr_appraisal.group_hr_appraisal_user")
            or user.has_group("base.group_system")
            or user in appraisal.manager_ids.mapped("user_id")
        ):
            return "all"
        if user in appraisal.employee_feedback_ids.mapped("user_id"):
            return "own"
        return None

    def _get_domain_results_page_user_input(self, survey, **post):
        user_input_domain = super()._get_domain_results_page_user_input(survey, **post)
        appraisal_id = self._get_id_param(post, "appraisal_id")
        if not appraisal_id:
            return user_input_domain
        appraisal = request.env["hr.appraisal"].sudo().browse(appraisal_id)
        role = self._appraisal_results_role(appraisal)
        if not role:
            raise AccessDenied
        user_input_domain &= Domain("appraisal_id", "=", appraisal.id)
        if role == "own":
            user_input_domain &= Domain(
                "partner_id", "=", request.env.user.partner_id.id
            )
        return user_input_domain

    @http.route(
        "/appraisal/<int:appraisal_id>/results", type="http", auth="user", website=True
    )
    def appraisal_survey_results(self, appraisal_id, **post):
        appraisal = request.env["hr.appraisal"].sudo().browse(int(appraisal_id))
        if appraisal.employee_id.user_id == request.env.user:
            return request.env["ir.http"]._serve_error_page(
                request.env._("Oops"),
                request.env._(
                    "Sorry, you can't access to this survey concerning your appraisal..."
                ),
                status=403,
            )
        user = request.env.user
        role = self._appraisal_results_role(appraisal)
        if not role:
            raise AccessDenied
        survey_id = self._get_id_param(post, "survey_id")
        answers_sudo = (
            request.env["survey.user_input"]
            .sudo()
            .search(
                [("appraisal_id", "=", appraisal.id)],
                order="create_date desc, id desc",
            )
        )
        if role == "own":
            answers_sudo = answers_sudo.filtered(
                lambda answer: answer.partner_id == user.partner_id
            )
        appraisal_surveys_sudo = answers_sudo.survey_id
        if survey_id:
            survey_sudo = appraisal_surveys_sudo.filtered(
                lambda survey: survey.id == survey_id
            )
        else:
            survey_sudo = appraisal_surveys_sudo[:1]
        if not survey_sudo:
            raise AccessDenied

        post["appraisal_id"] = appraisal_id
        user_input_lines_sudo, search_filters = self._extract_filters_data(
            survey_sudo, post
        )
        survey_data = survey_sudo._prepare_survey_statistics(user_input_lines_sudo)
        question_and_page_data = (
            survey_sudo.question_and_page_ids._prepare_question_statistics(
                user_input_lines_sudo
            )
        )

        answers = answers_sudo.filtered(
            lambda answer: answer.survey_id == survey_sudo and answer.state == "done"
        )

        requestors = answers.mapped("create_uid.partner_id")

        template_values = {
            "survey": survey_sudo,
            "answers": answers,
            "question_and_page_data": question_and_page_data,
            "survey_data": survey_data,
            "search_filters": search_filters,
            "search_finished": "true",
            "appraisal_id": appraisal_id,
            "appraisal_date": appraisal.date_close,
            "employee_name": appraisal.employee_id.name,
            "requestors": requestors,
        }
        return request.render("survey.survey_page_statistics", template_values)

    @http.route('/survey/results/<model("survey.survey"):survey>', type="http")
    def survey_report(self, survey, **post):
        if post.get("appraisal_id"):
            post["finished"] = "true"
        return super().survey_report(survey, **post)
