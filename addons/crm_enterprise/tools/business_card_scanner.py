import logging

import requests

from odoo import Command
from odoo.exceptions import UserError
from odoo.fields import Domain

_logger = logging.getLogger(__name__)

PROMPT = (
    "Extract details from the provided business card image as a JSON object. "
    "I will use the response you give me to extract data in an automated process so respect instructions or else it will fail. "
    "I will specify a list of the information I need, do NOT add anything else."
    "Consider this request with a very low temperature, DO NOT GUESS or try to be creative, only use the text you can read on the image, do not make things up! "
    "I don't want to see anything like 'Not specified' or 'Unknown' in the resulting JSON, don't specify the fields if you don't know. "
    "If you do not have AT LEAST a 'contact_name' OR a 'company_name', return an empty JSON. "
    "Reply with ONLY the JSON object on a SINGLE LINE, without code editor or styling. "
    "Here are the information I need, the field name in your resulting JSON is specified each time between quotes: "
    "- The name of the company, as 'partner_name' "
    "- The name of the contact (the person), as 'contact_name' "
    "- The main phone number (only ONE), as 'phone' "
    "- The main email address (only ONE), as 'email_from' "
    "- The company or contact website (only ONE), as 'website' "
    "- The Job Position, as 'function' "
    "- The city as 'city' "
    "- The zip code as 'zip' "
    "- The state code as 'state_code', it needs to be a code and not the full name (example: Q1 for London), if you don't know the code, don't specify this field "
    "- The country code as 'country_code', in a 2 characters ISO code (NOT 3 characters, 2), if you don't know the ISO code, don't specify this field "
    "- The first part of the address that is not in the above fields, usually the street and number, as 'street' "
    "- The second part of the address, only if it is obvious there are 2 parts, as 'street2' "
)


class BusinessCardScanner:
    def __init__(self, env) -> None:
        self.env = env

    def business_cards_to_leads(self, attachments):
        """Create opportunities from the details extracted from images of business cards."""

        valid_attachments = []
        lead_values_list = []

        for attachment in attachments:
            try:
                extracted_data = self.env["crm.lead"]._read_business_card(attachment)
            except requests.exceptions.RequestException as error:
                raise UserError(
                    self.env._("Network error while processing the business cards.")
                ) from error

            if not extracted_data:
                continue

            # Normalize to list of dicts
            if isinstance(extracted_data, dict):
                extracted_data = [extracted_data]

            fields_allowlist = [
                "partner_name",
                "contact_name",
                "email_from",
                "phone",
                "website",
                "function",
                "street",
                "street2",
                "zip",
            ]

            for data in extracted_data:
                lead_values = {
                    field: data[field].strip()
                    for field in fields_allowlist
                    if data.get(field)
                }
                lead_values["type"] = "opportunity"

                contact_name = lead_values.get("contact_name")
                company_name = lead_values.get("partner_name")
                if contact_name or company_name:
                    lead_values["name"] = self.env._(
                        "%(contact_name)s's opportunity",
                        contact_name=contact_name or company_name,
                    )
                else:
                    continue  # safety net as we told AI to return an empty result in this case

                # extract country
                country = False
                if data.get("country_code") and len(data["country_code"]) == 2:
                    country = self.env["res.country"].search(
                        [("code", "=", data["country_code"])], limit=1
                    )
                    if country:
                        lead_values["country_id"] = country.id

                # extract state
                if data.get("state_code"):
                    domain = Domain("code", "=", data["state_code"])
                    if country:
                        domain &= Domain("country_id", "=", country.id)
                    state = self.env["res.country.state"].search(domain, limit=1)
                    if state:
                        lead_values["state_id"] = state.id

                # format phone
                if phone := lead_values.pop("phone", False):
                    lead_values["phone_ids"] = [
                        Command.create(
                            {
                                "number": self.env["crm.lead"]._phone_format(
                                    number=phone, country=country
                                )
                                or phone,
                                "type": "landline",
                            }
                        )
                    ]

                lead_values_list.append(lead_values)
                valid_attachments.append(attachment)

        if len(attachments) == 1 and not lead_values_list:
            # special case when a single attachment fails: do not create records
            # caller is responsible for followup behavior and feedback in that case
            return self.env["crm.lead"]

        leads = self.env["crm.lead"].create(lead_values_list)
        for lead, attachment in zip(leads, valid_attachments, strict=True):
            attachment.write({"res_model": "crm.lead", "res_id": lead.id})

            lead._message_log(
                body=self.env._("Lead generated from this image."),
                attachment_ids=[attachment.id],
            )

        # create "empty leads" for failing images to give better user feedback
        invalid_attachments = attachments.filtered(
            lambda attachment: attachment not in valid_attachments
        )
        empty_leads = self.env["crm.lead"].create(
            [
                {"name": self.env._("New Lead Scan")}
                for i in range(len(invalid_attachments))
            ]
        )
        for lead, attachment in zip(empty_leads, invalid_attachments, strict=True):
            attachment.write({"res_model": "crm.lead", "res_id": lead.id})

            lead._message_log(
                body=self.env._("Could not extract lead information from this image."),
                attachment_ids=[attachment.id],
            )

        return leads + empty_leads
