from odoo import fields
from odoo.tests import tagged

from odoo.addons.account.tests.common_report_engine import TestAccountReportsCommon


@tagged("post_install", "-at_install")
class TestReports(TestAccountReportsCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.report = cls.env.ref("account.balance_sheet")
        # A folder is an access boundary, and the company's accounting folder
        # is one a deployment may well have closed, leaving the accountant who
        # exports the report outside it: the create is then refused on the
        # folder, which says nothing about the values this test is here for.
        # So the export goes to a folder of its own, open to internal users.
        cls.export_folder = (
            cls.env["document.document"]
            .sudo()
            .create(
                {
                    "name": "Report Export Folder",
                    "type": "folder",
                    "access_internal": "edit",
                }
            )
        )
        cls.env.company.sudo().account_folder_id = cls.export_folder

    def test_report_export_wizard(self):
        """The wizard in documents_account overrides the one in account.

        This test makes sure that the folder_id and tag_ids are properly set on _prepare_attachment_vals().
        """
        options = self._generate_options(
            self.report,
            fields.Date.from_string("2017-02-01"),
            fields.Date.from_string("2017-02-01"),
        )

        action = self.report.open_report_export_wizard(options)

        wizard = self.env[action["res_model"]].browse(action["res_id"])
        wizard = wizard.with_context(account_report_generation_options=options)
        export_format_ids = self.env[
            "wizard.report.formula.export.attachment.format"
        ].search([("fun_param", "=", "export_to_xlsx")])
        wizard["export_format_ids"] = export_format_ids

        wizard.export_report()

        self.assertTrue(
            self.env["document.document"].search(
                [("folder_id", "=", self.export_folder.id)]
            ),
            "the generated files are filed in the folder the wizard carries",
        )
