from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {"active_test": False})
    returns = env["account.return"].search([("country_id", "=", False)])
    for (return_type, company), type_returns in returns.grouped(
        lambda account_return: (account_return.type_id, account_return.company_id)
    ).items():
        if country := return_type._get_filing_country(company):
            type_returns.country_id = country
