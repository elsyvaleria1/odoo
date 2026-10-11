from . import models
from odoo.addons.account_batch_payment.models.sepa_mapping import (
    normalize_communication,
)


def init_initiating_party_names(env) -> None:
    for company in env["res.company"].search([]):
        company.iso20022_initiating_party_name = normalize_communication(company.name)
