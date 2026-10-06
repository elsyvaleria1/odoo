from odoo.addons.account.tests.common_report_engine import TestAccountReportsCommon
from odoo.addons.report_formula.models.account_report_custom_handler import (
    AccountReportFileDownloadException,
)


class TestSaftReport(TestAccountReportsCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.company_data["company"]
        cls.ReportException = AccountReportFileDownloadException
        cls.ReportModel = cls.env.ref("account.general_ledger_report")
        cls.ReportHandlerModel = cls.env[cls.ReportModel.custom_handler_model_name]
        cls.report_handler = cls.ReportHandlerModel.with_company(company)

    def _generate_options(self, date_from="2023-10-01", date_to="2023-10-31"):
        return super()._generate_options(self.ReportModel, date_from, date_to)
