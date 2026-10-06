from odoo import api, fields, models
from odoo.tools import SQL, frozendict

# Real move ids are positive int4, order ids are negative int4. Templates use
# the next positive namespace, stable across inserts and exactly representable
# by JavaScript. The UNION promotes its virtual id column to bigint.
TEMPLATE_SOURCE_ID_OFFSET = 2**31


class MixinAccountDocumentMatch(models.AbstractModel):
    _inherit = "mixin.account.document.match"
    _depends = frozendict(
        {
            "account.move.template": [
                "active",
                "company_id",
                "is_payment",
                "move_type",
                "name",
                "partner_id",
                "ref",
            ],
            "res.company": ["currency_id"],
        }
    )

    template_id = fields.Many2one(
        comodel_name="account.move.template",
        readonly=True,
    )

    @api.depends("currency_id", "name", "reference", "amount", "template_id")
    def _compute_display_name(self):
        templates = self.filtered("template_id")
        for doc in templates:
            label = doc.name or ""
            if doc.reference:
                label += " - " + doc.reference
            doc.display_name = label + " (" + self.env._("Template") + ")"
        super(MixinAccountDocumentMatch, self - templates)._compute_display_name()

    @api.model
    def _get_document_columns(self):
        return {**super()._get_document_columns(), "template_id": SQL("NULL::INTEGER")}

    @api.model
    def _get_additional_queries(self):
        queries = super()._get_additional_queries()
        Template = self.env["account.move.template"]
        if Template.has_access("read"):
            domain = [
                ("active", "=", True),
                ("is_payment", "=", False),
                ("move_type", "in", self._get_source_move_types()),
            ]
            # Use the source model's ORM query, including its access policies.
            readable = Template._search(domain)
            lang = self.env.lang or "en_US"
            values = {
                "id": SQL("%s::BIGINT + template.id", TEMPLATE_SOURCE_ID_OFFSET),
                "name": SQL(
                    "COALESCE(template.name->>%s, template.name->>'en_US', "
                    "(SELECT value FROM jsonb_each_text(template.name) LIMIT 1))::VARCHAR",
                    lang,
                ),
                "reference": SQL("template.ref"),
                "partner_id": SQL("template.partner_id"),
                "date": SQL("DATE '9999-12-31'"),
                "currency_id": SQL(
                    "COALESCE(rc.currency_id, %s)", self.env.company.currency_id.id
                ),
                "company_id": SQL("template.company_id"),
                "template_id": SQL("template.id"),
                "move_type": SQL("template.move_type"),
            }
            queries.append(
                SQL(
                    "SELECT %s FROM account_move_template template "
                    "LEFT JOIN res_company rc ON rc.id = template.company_id "
                    "WHERE template.id IN (%s)",
                    self._select_document_columns(values),
                    readable.select(),
                )
            )
        return queries
