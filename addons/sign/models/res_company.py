from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    sign_terms = fields.Html(
        string="Sign Default Terms and Conditions",
        translate=True,
        default="""<h1 style="text-align: center; ">Terms &amp; Conditions</h1>
        <p>Your conditions...</p>""",
    )
    sign_terms_type = fields.Selection(
        selection=[("plain", "Terms in Email"), ("html", "Terms as Web Page")],
        string="Sign Terms & Conditions format",
        default="plain",
        help="""Terms in Email - The text will be displayed at the bottom of every signature request email.\n
        Terms as Web Page - A link will be pasted at the bottom of every signature request email, leading to your content.
        """,
    )
    sign_terms_html = fields.Html(
        string="Sign Default Terms and Conditions as a Web page",
        translate=True,
        sanitize_attributes=False,
        default="""<h1 style="text-align: center; ">Terms &amp; Conditions</h1>
        <p>Your conditions...</p>""",
    )

    signing_certificate_id = fields.Many2one(comodel_name="certificate.certificate")
