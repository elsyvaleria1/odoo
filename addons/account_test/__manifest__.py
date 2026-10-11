# Copyright (c) 2011 CCI Connect asbl (http://www.cciconnect.be) All Rights Reserved.
#                       Philmer <philmer@cciconnect.be>

{
    "name": "Accounting Consistency Checks",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Run configurable checks against accounting data",
    "description": "Provide accounting test definitions and a report of their execution results. Authorized users configure the code used to check accounting consistency.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account",
    ],
    "data": [
        "security/ir.access.csv",
        "views/accounting_assert_test_views.xml",
        "reports/accounting_assert_test_reports.xml",
        "data/accounting_assert_test_data.xml",
        "reports/report_account_test_templates.xml",
        "views/account_test_menus.xml",
    ],
}
