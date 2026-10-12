from odoo import api, fields, models
from odoo.exceptions import AccessError
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps

from odoo.addons.spreadsheet.utils.formatting import (
    date_to_spreadsheet_date_number,
    datetime_to_spreadsheet_date_number,
)

_debug = DebugLog(__name__)


class Survey(models.Model):
    _inherit = "survey.survey"

    spreadsheet_document_id = fields.Many2one(
        comodel_name="document.document",
        copy=False,
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        if any("spreadsheet_document_id" in vals for vals in vals_list):
            self._check_spreadsheet_link_is_the_systems()
        return super().create(vals_list)

    def write(self, vals):
        if "spreadsheet_document_id" in vals:
            self._check_spreadsheet_link_is_the_systems()
        return super().write(vals)

    def _check_spreadsheet_link_is_the_systems(self) -> None:
        if not self.env.su:
            _debug.logic("survey_spreadsheet_link_refused", user=self.env.user)
            raise AccessError(
                self.env._("The results spreadsheet of a survey is set by Odoo.")
            )

    def get_survey_results_for_spreadsheet(self) -> list:
        return [survey._get_survey_values() for survey in self]

    def _get_survey_values(self) -> dict:
        self.check_singleton()

        locale = self.env["res.lang"]._get_user_spreadsheet_locale()
        date_format = locale["dateFormat"]
        date_time_format = locale["dateFormat"] + " " + locale["timeFormat"]
        tz_name = self.env.user.tz or "UTC"

        n_of_rows = len(self.user_input_ids) + 1
        result = []
        timestamp_column = [{"value": ""} for _ in range(n_of_rows)]
        timestamp_column[0]["value"] = self.env._("Timestamp")
        result.append(timestamp_column)
        if self.users_login_required:
            user_id_column = [{"value": ""} for _ in range(n_of_rows)]
            user_id_column[0]["value"] = self.env._("User")
            result.append(user_id_column)
        if self.is_attempts_limited:
            attempt_column = [{"value": ""} for _ in range(n_of_rows)]
            attempt_column[0]["value"] = self.env._("Attempts")
            result.append(attempt_column)
        if self.scoring_type != "no_scoring":
            scoring_column = [{"value": ""} for _ in range(n_of_rows)]
            scoring_column[0]["value"] = self.env._("Score (%)")
            result.append(scoring_column)
        if self.scoring_type != "no_scoring" and self.scoring_success_min:
            test_passed_column = [{"value": ""} for _ in range(n_of_rows)]
            test_passed_column[0]["value"] = self.env._("Quiz passed")
            result.append(test_passed_column)

        user_inputs = self.user_input_ids.sorted("create_date")
        user_row_index = {}
        for index, user_input in enumerate(user_inputs):
            user_row_index[user_input] = index + 1
            timestamp_column[index + 1]["value"] = datetime_to_spreadsheet_date_number(
                user_input.create_date, tz_name
            )
            timestamp_column[index + 1]["format"] = date_time_format
            if self.users_login_required:
                user_id_column[index + 1]["value"] = user_input.partner_id.name
            if self.is_attempts_limited:
                attempt_column[index + 1]["value"] = user_input.attempts_number
                attempt_column[index + 1]["format"] = '0"/%s"' % self.attempts_limit
            if self.scoring_type != "no_scoring":
                scoring_column[index + 1]["value"] = (
                    user_input.scoring_percentage / 100.0
                )
                scoring_column[index + 1]["format"] = "0.00%"
            if self.scoring_type != "no_scoring" and self.scoring_success_min:
                test_passed_column[index + 1]["value"] = user_input.scoring_success

        for question in self.question_ids:
            if question.question_type in {"simple_choice", "multiple_choice"}:
                column = [{"value": ""} for _ in range(n_of_rows)]
                column[0]["value"] = question.title
                comment_column = [{"value": ""} for _ in range(n_of_rows)]
                comment_column[0]["value"] = "{} - {}".format(
                    self.env._("Comments"), question.title
                )

                lines_by_input = question.user_input_line_ids.grouped("user_input_id")
                no_lines = question.user_input_line_ids.browse()
                for user_input in self.user_input_ids:
                    answers, comments = self._get_answer_lines_and_comments(
                        question, lines_by_input.get(user_input, no_lines)
                    )
                    column[user_row_index[user_input]]["value"] = ", ".join(
                        answers.mapped("display_name")
                    )
                    if comments:
                        comment_column[user_row_index[user_input]]["value"] = ", ".join(
                            comments.mapped("display_name")
                        )
                result.append(column)
                if question.comments_allowed and not question.comment_count_as_answer:
                    result.append(comment_column)
            elif question.question_type == "matrix":
                answers_by_row = question.user_input_line_ids.grouped("matrix_row_id")
                for matrix_row in question.matrix_row_ids:
                    answers_of_row = answers_by_row.get(
                        matrix_row, question.user_input_line_ids.browse()
                    )
                    column = [{"value": ""} for _ in range(n_of_rows)]
                    column[0]["value"] = question.title + " [" + matrix_row.value + "]"
                    for user_input, input_lines in answers_of_row.grouped(
                        "user_input_id"
                    ).items():
                        column[user_row_index[user_input]]["value"] = ", ".join(
                            input_lines.mapped("suggested_answer_id.value")
                        )
                    result.append(column)
                if question.comments_allowed:
                    comment_column = [{"value": ""} for _ in range(n_of_rows)]
                    comment_column[0]["value"] = "{} - {}".format(
                        self.env._("Comments"), question.title
                    )
                    for comment_input in question.user_input_line_ids.filtered(
                        lambda x: x.answer_type == "char_box"
                    ):
                        comment_column[user_row_index[comment_input.user_input_id]][
                            "value"
                        ] = comment_input._get_answer_value()
                    result.append(comment_column)
            else:
                column = [{"value": ""} for _ in range(n_of_rows)]
                column[0]["value"] = question.title
                for user_input_line in question.user_input_line_ids:
                    value = user_input_line._get_answer_value()
                    value_format = None
                    if user_input_line.answer_type == "datetime" and value:
                        value = datetime_to_spreadsheet_date_number(value, tz_name)
                        value_format = date_time_format
                    elif user_input_line.answer_type == "date" and value:
                        value = date_to_spreadsheet_date_number(value)
                        value_format = date_format
                    column[user_row_index[user_input_line.user_input_id]]["value"] = (
                        value
                    )
                    if value_format:
                        column[user_row_index[user_input_line.user_input_id]][
                            "format"
                        ] = value_format
                result.append(column)

        _debug.pipeline(
            "survey_spreadsheet_table_built",
            survey=self,
            columns=len(result),
            rows=n_of_rows,
            questions=len(self.question_ids),
        )
        return {
            "survey_name": self.title,
            "survey_table": result,
            "user_input_ids": user_inputs.ids,
        }

    def action_survey_open_linked_spreadsheet(self) -> dict:
        self.check_singleton()
        self.check_access("write")
        survey_folder_sudo = self._get_or_create_survey_folder_sudo()
        _debug.logic(
            "survey_spreadsheet_opened",
            survey=self,
            action="reused" if self.spreadsheet_document_id else "created",
        )
        if not self.spreadsheet_document_id:
            title = f"{self.title} (#{self.id})"
            open_spreadsheet_action = (
                self.env["document.document"]
                .sudo()
                .action_view_new_spreadsheet(
                    {
                        "name": title,
                        "folder_id": survey_folder_sudo.id,
                        "owner_id": False,
                        "spreadsheet_data": json_dumps(
                            self._prepare_spreadsheet_data()
                        ),
                    }
                )
            )
            spreadsheet_id = open_spreadsheet_action["params"]["spreadsheet_id"]

            self.sudo().spreadsheet_document_id = spreadsheet_id

        self.spreadsheet_document_id.sudo().action_update_access_rights(
            partners={self.env.user.partner_id.id: ("edit", False)}
        )

        if not self.spreadsheet_document_id.active:
            self.spreadsheet_document_id.sudo().action_unarchive()

        return {
            "type": "ir.actions.client",
            "tag": "action_view_spreadsheet",
            "params": {
                "spreadsheet_id": self.spreadsheet_document_id.id,
            },
        }

    def _get_answer_lines_and_comments(self, question, input_lines) -> tuple:
        answers = input_lines.filtered(
            lambda line: (
                line.answer_type != "char_box" or question.comment_count_as_answer
            )
        )
        comments = None
        if question.comments_allowed and not question.comment_count_as_answer:
            comments = input_lines.filtered(lambda line: line.answer_type == "char_box")
        return answers, comments

    def _prepare_spreadsheet_data(self) -> dict:
        self.check_singleton()

        lang = self.env["res.lang"]._get_lang_cached(self.env.user.lang)
        locale = lang._odoo_lang_to_spreadsheet_locale()

        survey_data = self._get_survey_values()
        number_of_columns = len(survey_data["survey_table"])
        number_of_rows = len(survey_data["survey_table"][0])

        style_range = (
            f"A1:{number_to_letters(number_of_columns - 1)}1"
            if number_of_columns > 1
            else "A1"
        )

        sheet = {
            "id": "sheet1",
            "name": f"{self.title} (#{self.id})",
            "cols": {str(i): {"size": 150} for i in range(number_of_columns)},
            "colNumber": max(26, number_of_columns),
            "rowNumber": max(100, number_of_rows),
            "cells": {"A1": f"=ODOO.SURVEY({self.id})"},
            "styles": {style_range: 1},
            "panes": {"ySplit": 1, "xSplit": 0},
        }

        return {
            "version": "18.4.2",
            "sheets": [sheet],
            "settings": {
                "locale": locale,
            },
            "styles": {"1": {"bold": True}},
            "revisionId": "START_REVISION",
        }

    @api.model
    def _get_or_create_survey_folder_sudo(self):
        folder_id = self.env.registry.settings.get(
            self.env, "document_spreadsheet_survey.survey_folder", False
        )
        folder_sudo = self.env["document.document"].sudo().browse(int(folder_id))
        if not folder_sudo or not folder_sudo.exists():
            folder_sudo = (
                self.env["document.document"]
                .sudo()
                .create(
                    {
                        "name": self.env._("Survey"),
                        "type": "folder",
                        "access_internal": "none",
                        "access_via_link": "none",
                        "owner_id": False,
                    }
                )
            )
            self.env["ir.config_parameter"].sudo().set_param(
                "document_spreadsheet_survey.survey_folder", folder_sudo.id
            )
            _debug.logic(
                "survey_spreadsheet_folder",
                folder=folder_sudo,
                action="created",
                stale_param=folder_id,
            )
        elif not folder_sudo.active:
            _debug.logic(
                "survey_spreadsheet_folder", folder=folder_sudo, action="unarchived"
            )
            folder_sudo.action_unarchive()

        return folder_sudo


def number_to_letters(n: int) -> str:
    if n < 0:
        raise ValueError(f"number must be positive. Got {n}")
    if n < 26:
        return chr(65 + n)
    else:
        return number_to_letters(n // 26 - 1) + number_to_letters(n % 26)
