from odoo.exceptions import AccessError
from odoo.libs.json import loads as json_loads

from odoo.addons.document_spreadsheet.tests.common import SpreadsheetTestCommon
from odoo.addons.survey.tests.common import TestSurveyCommon


class DocumentSpreadsheetSurveyAction(TestSurveyCommon, SpreadsheetTestCommon):
    def test_action_survey_open_linked_spreadsheet(self):
        test_survey = self.env["survey.survey"].create({"title": "Test Survey"})
        self.assertFalse(test_survey.spreadsheet_document_id)

        action = test_survey.action_survey_open_linked_spreadsheet()
        linked_spreadsheet = test_survey.spreadsheet_document_id
        self.assertEqual(
            action,
            {
                "type": "ir.actions.client",
                "tag": "action_view_spreadsheet",
                "params": {
                    "spreadsheet_id": linked_spreadsheet.id,
                },
            },
        )
        self.assertEqual(linked_spreadsheet.name, "Test Survey (#%s)" % test_survey.id)

        # Re-calling the action should return the same spreadsheet
        action = test_survey.action_survey_open_linked_spreadsheet()
        self.assertEqual(
            action["params"],
            {
                "spreadsheet_id": linked_spreadsheet.id,
            },
        )

    def test_action_survey_open_linked_spreadsheet_initial_data(self):
        test_survey = self.env["survey.survey"].create({"title": "Test Survey"})
        question_0 = self._add_question(
            None,
            "What is your age",
            "numerical_box",
            survey_id=test_survey.id,
            sequence=1,
        )
        answer_0 = self._add_answer(test_survey, self.customer)
        self._add_answer_line(question_0, answer_0, 25)

        test_survey.action_survey_open_linked_spreadsheet()
        binary_data = test_survey.spreadsheet_document_id.spreadsheet_data
        data = json_loads(binary_data)

        self.assertEqual(data["version"], "18.4.2")
        self.assertEqual(len(data["sheets"]), 1)
        sheet = data["sheets"][0]
        self.assertEqual(sheet["name"], "Test Survey (#%s)" % test_survey.id)
        self.assertEqual(sheet["cells"]["A1"], "=ODOO.SURVEY(%s)" % test_survey.id)
        self.assertEqual(sheet["cols"]["0"]["size"], 150)
        self.assertEqual(sheet["cols"]["1"]["size"], 150)
        self.assertEqual(sheet["panes"]["ySplit"], 1)

    def test_archived_linked_spreadsheet(self):
        test_survey = self.env["survey.survey"].create({"title": "Test Survey"})

        # Spreadsheet is restored when opening the action again
        test_survey.spreadsheet_document_id.action_archive()
        self.assertFalse(test_survey.spreadsheet_document_id.active)

        test_survey.action_survey_open_linked_spreadsheet()
        self.assertTrue(test_survey.spreadsheet_document_id.active)

        # Survey folder is restored as well
        folder_id = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("document_spreadsheet_survey.survey_folder", False)
        )
        folder = self.env["document.document"].browse(int(folder_id))

        folder.action_archive()
        test_survey.spreadsheet_document_id.action_archive()
        self.assertFalse(test_survey.spreadsheet_document_id.active)
        self.assertFalse(folder.active)

        test_survey.action_survey_open_linked_spreadsheet()
        self.assertTrue(test_survey.spreadsheet_document_id.active)
        self.assertTrue(folder.active)

    def test_an_officer_cannot_point_a_survey_at_a_document_to_take_it(self):
        private = (
            self.env["document.document"]
            .with_user(self.survey_manager)
            .create({"name": "Private", "type": "folder", "user_folder_id": "MY"})
        )
        Survey = self.env["survey.survey"].with_user(self.survey_user)
        with self.assertRaises(AccessError):
            Survey.create({"title": "Grab", "spreadsheet_document_id": private.id})
        survey = Survey.create({"title": "Grab"})
        with self.assertRaises(AccessError):
            survey.spreadsheet_document_id = private
        self.assertEqual(private.with_user(self.survey_user).user_permission, "none")

        # the action still links, opens and shares the survey's own sheet
        action = survey.action_survey_open_linked_spreadsheet()
        sheet = survey.spreadsheet_document_id
        self.assertEqual(action["params"]["spreadsheet_id"], sheet.id)
        self.assertEqual(sheet.with_user(self.survey_user).user_permission, "edit")
