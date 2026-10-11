from odoo import models


class BaseModel(models.AbstractModel):
    _inherit = "base"

    def _sms_get_recipients_info(self, force_field=False, partner_fallback=True):
        result = dict.fromkeys(self.ids, False)
        fnames = [force_field] if force_field else self._get_phone_number_fields()
        fnames = [fname for fname in fnames if fname in self._fields]
        field_store = fnames[0] if fnames else False
        partners_by_record = self._mail_get_partners()
        prefetch = self.env["phone.number"].browse()
        for fname in fnames:
            prefetch |= self.mapped(fname)
        for partners in partners_by_record.values():
            prefetch |= partners.mapped("phone_ids")
        prefetch.fetch(["number", "sanitized", "type", "primary", "sequence", "valid"])
        for record in self:
            all_partners = partners_by_record[record.id]
            phone = record._phone_get_numbers(fname=force_field)._primary(
                "mobile", "whatsapp"
            )

            if phone.valid:
                result[record.id] = {
                    "partner": all_partners[0]
                    if all_partners
                    else self.env["res.partner"],
                    "sanitized": phone.sanitized,
                    "number": phone.number,
                    "partner_store": False,
                    "field_store": field_store,
                }
            elif all_partners and partner_fallback:
                partner_phone = self.env["phone.number"]
                for partner in all_partners:
                    partner_phone = partner._phone_get_number("mobile", "whatsapp")
                    if partner_phone.valid:
                        break

                result[record.id] = {
                    "partner": partner,
                    "sanitized": partner_phone.sanitized
                    if partner_phone.valid
                    else False,
                    "number": partner_phone.number or False,
                    "partner_store": True,
                    "field_store": "phone_ids",
                }
            else:
                result[record.id] = {
                    "partner": self.env["res.partner"],
                    "sanitized": False,
                    "number": phone.number or False,
                    "partner_store": False,
                    "field_store": field_store,
                }
        return result
