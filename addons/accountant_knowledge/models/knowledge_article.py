import ast
import re

from lxml import html

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads


class KnowledgeArticle(models.Model):
    _name = "knowledge.article"
    _inherit = ["knowledge.article"]

    audit_report_id = fields.One2many(
        comodel_name="audit.report",
        inverse_name="knowledge_article_id",
    )
    inherited_audit_report_id = fields.One2many(
        comodel_name="audit.report",
        compute="_compute_inherited_audit_report",
        store=False,
    )
    is_audit_report_template = fields.Boolean(string="Audit Report Template")

    @api.depends("audit_report_id")
    def _compute_inherited_audit_report(self) -> None:
        for article in self:
            current = article
            while current and not current.audit_report_id:
                current = current.parent_id
            article.inherited_audit_report_id = (
                current.audit_report_id
                if current and current.audit_report_id
                else False
            )

    def update_embedded_audit_report_options(
        self, html_element_host_id, new_options
    ) -> None:
        self.check_singleton()
        fragment = html.fragment_fromstring(self.body, create_parent=True)
        selector = f'.//*[@data-embedded="accountReport"][@data-oe-id="{html_element_host_id}"]'
        for element in fragment.findall(selector):
            element.set(
                "data-embedded-props",
                json_dumps(
                    {
                        **json_loads(element.get("data-embedded-props")),
                        "options": new_options,
                    }
                ),
            )
        elements = [
            html.tostring(child, encoding="unicode", method="html")
            for child in fragment.getchildren()
        ]
        self.write({"body": "".join(elements)})

    @api.model
    def _get_domain_available_template(self):
        base_domain = super()._get_domain_available_template()
        return Domain.AND([base_domain, [("is_audit_report_template", "=", False)]])

    def _get_inherited_audit_report(self):
        self.check_singleton()
        reports = self.env["audit.report"]
        if not reports.has_access("read"):
            return reports
        return self.inherited_audit_report_id

    def _prepare_template(self, ref):
        fragment = super()._prepare_template(ref)
        if "target_article_id" in self.env.context:
            target_article = self.env["knowledge.article"].browse(
                self.env.context["target_article_id"]
            )
            audit_report = target_article._get_inherited_audit_report()

            def transform_xmlid_to_res_id(match):
                return str(ref(match.group("xml_id")))

            for element in fragment.xpath('//*[@data-embedded="accountReport"]'):
                embedded_props = ast.literal_eval(
                    re.sub(
                        r"(?<![\w])ref\(\'(?P<xml_id>\w+\.\w+)\'\)",
                        transform_xmlid_to_res_id,
                        element.get("data-embedded-props"),
                    )
                )
                if "options" in embedded_props:
                    account_report_options = embedded_props["options"]
                    if "report_id" in account_report_options:
                        account_report = self.env["report.formula"].browse(
                            account_report_options["report_id"]
                        )
                        embedded_props["options"] = account_report.get_options(
                            {
                                "selected_variant_id": account_report.id,
                                "date": {
                                    "date_from": str(audit_report.start_date),
                                    "date_to": str(audit_report.end_date),
                                    "mode": "range",
                                    "filter": "custom",
                                },
                                **embedded_props["options"],
                            }
                        )
                element.set("data-embedded-props", json_dumps(embedded_props))
        else:
            for element in fragment.xpath('//*[@data-embedded="accountReport"]'):
                embedded_props = ast.literal_eval(
                    re.sub(
                        r"(?<![\w])ref\(\'(?P<xml_id>\w+\.\w+)\'\)",
                        lambda match: "0",
                        element.get("data-embedded-props"),
                    )
                )
                element.set(
                    "data-embedded-props",
                    json_dumps({"name": embedded_props.get("name"), "options": {}}),
                )

        return fragment
