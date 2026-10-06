from odoo import api, models

LEAD_FIELDS = {
    "person_name": "contact_name",
    "company_name": "partner_name",
    "job_title": "function",
    "email": "email_from",
    "phone": "phone",
    "website": "website",
    "street": "street",
    "street2": "street2",
    "city": "city",
    "zip": "zip",
    "state_code": "state_code",
    "country_code": "country_code",
}


class CrmLead(models.Model):
    _inherit = "crm.lead"

    @api.model
    def _read_business_card(self, attachment):
        attachment.extract_document_type = "business_card"
        result = attachment._extract_document()
        cards = result and "cards" in result and result["cards"].value
        if not cards:
            return super()._read_business_card(attachment)
        return [
            {
                LEAD_FIELDS[key]: value
                for key, value in card.items()
                if key in LEAD_FIELDS
            }
            for card in cards
        ]
