from odoo import fields, models
from odoo.libs.text import plaintext_link_spans


class SmsSms(models.Model):
    _inherit = "sms.sms"

    mailing_id = fields.Many2one(
        comodel_name="mailing.mailing",
        string="Mass Mailing",
    )
    # Linking to another field than the comodel id allows to use the ORM to create
    # "linked" records (see _prepare_sms_values) without adding a foreign key.
    # See commit message for why this is useful.
    mailing_trace_ids = fields.One2many(
        comodel_name="mailing.trace",
        inverse_name="sms_id_int",
        string="Statistics",
    )

    def _update_body_short_links(self):
        """Override to tweak shortened URLs by adding statistics ids, allowing to
        find customer back once clicked."""
        res = dict.fromkeys(self.ids, False)
        for sms in self:
            if not sms.mailing_id or not sms.body:
                res[sms.id] = sms.body
                continue

            body = sms.body
            short_prefix = sms.get_base_url() + "/r/"
            parts = []
            idx = 0
            for start, end in plaintext_link_spans(body):
                if body.startswith(short_prefix, start, end):
                    parts += (body[idx:end], f"/s/{sms.id}")
                    idx = end
            parts.append(body[idx:])
            res[sms.id] = "".join(parts)
        return res
