from odoo import fields, models


class MixinMailComposerAI(models.AbstractModel):
    _inherit = "mixin.mail.composer"

    body = fields.Html(eval_ai_prompts=True)
