from odoo import fields, models


class MailTemplateAI(models.Model):
    _inherit = "mail.template"

    body_html = fields.Html(eval_ai_prompts=True)

    def _check_rendering(self, fnames=None, render_options=None):
        """Override to ensure that the prompts are not evaluated during checks."""
        render_options = {**(render_options or {}), "eval_ai_prompts": False}
        return super()._check_rendering(fnames=fnames, render_options=render_options)
