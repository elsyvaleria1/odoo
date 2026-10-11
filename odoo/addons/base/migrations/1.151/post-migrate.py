from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    companies = env["res.company"].search([("resource_calendar_id", "=", False)])
    main = env.ref("base.main_company", raise_if_not_found=False)
    standard = env.ref("base.resource_calendar_std", raise_if_not_found=False)
    if main in companies and standard and standard.company_id == main:
        main.resource_calendar_id = standard
        companies -= main
    companies._create_resource_calendar()
