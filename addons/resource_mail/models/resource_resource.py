from odoo import fields, models


class ResourceResource(models.Model):
    _name = "resource.resource"
    _inherit = ["resource.resource", "mixin.mail.thread", "mixin.mail.activity"]

    im_status = fields.Char(related="user_id.im_status")

    def get_avatar_card_data(self, field_names):
        stored = [fname for fname in field_names if fname != "phone"]
        data = self.read(stored) if stored else [{"id": r.id} for r in self]
        if "phone" in field_names:
            for resource, values in zip(self, data, strict=True):
                values["phone"] = resource.partner_id.phone_ids._primary().number
        return data
