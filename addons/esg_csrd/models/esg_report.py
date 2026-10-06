from lxml import html

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads


class EsgReport(models.Model):
    _name = "esg.report"
    _description = "ESG Report"

    def _get_report_type_selection(self):
        selection = [
            ("vsme_basic", "VSME - Basic Module"),
            ("vsme_advanced", "VSME - Basic Module + Comprehensive Module"),
        ]
        if self.env.user.has_group("esg_csrd.group_esg_csrd_reporting"):
            selection.append(("csrd", "CSRD"))
        return selection

    report_type = fields.Selection(
        selection=lambda self: self._get_report_type_selection(),
        required=True,
    )
    color = fields.Integer(export_string_translation=False)
    knowledge_article_id = fields.Many2one(
        comodel_name="knowledge.article",
        index=True,
        required=True,
    )
    title = fields.Char(required=True)
    start_date = fields.Date(
        string="Reporting Date",
        compute="_compute_dates",
        precompute=True,
        store=True,
        readonly=False,
        required=True,
    )
    end_date = fields.Date(
        string="Reporting End Date",
        compute="_compute_dates",
        precompute=True,
        store=True,
        readonly=False,
        required=True,
    )
    responsible_user_ids = fields.Many2many(
        comodel_name="res.users",
        string="Responsibles",
        default=lambda self: self.env.user,
    )
    status = fields.Selection(
        selection=[("draft", "Draft"), ("done", "Done")],
        default="draft",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Group Reporting Company",
        default=lambda self: (
            self.env["res.company"].sudo().ESG_REPORT_DEFAULT_COMPANY
            or self.env.company
        ),
        required=True,
        help="This company defines the fiscal year and main company information used for the report. If your group has several companies, choose the one representing the consolidated perimeter.",
    )
    nace_id = fields.Many2one(
        comodel_name="esg.nace",
        string="NACE Code",
        default=lambda self: self.search([], order="create_date desc", limit=1).nace_id,
        help="Select the NACE code representing the company's main economic activity",
    )
    base_year = fields.Integer(
        default=lambda self: (
            self.search([], order="create_date desc", limit=1).base_year
        ),
        help="""Select the histrocial reference year for tracking progress on metrics like GHG emissions, energy or water.
            It serves as a benchmark for future comparisons and may be adjusted if major structural changes occur.
        """,
    )

    @api.depends("company_id")
    def _compute_dates(self) -> None:
        for report in self:
            dates = report.company_id.sudo().compute_fiscalyear_dates(
                fields.Date.today()
            )
            report.start_date = dates["date_from"]
            report.end_date = dates["date_to"]

    @api.model_create_multi
    def create(self, vals_list):
        root_articles = self.env["knowledge.article"].create(
            [
                {
                    "internal_permission": "none",
                    "article_member_ids": [
                        Command.create(
                            {
                                "partner_id": self.env.user.partner_id.id,
                                "permission": "write",
                            }
                        )
                    ],
                }
                for _ in vals_list
            ]
        )
        for vals, root_article in zip(vals_list, root_articles, strict=False):
            vals["knowledge_article_id"] = root_article.id

        esg_reports = super().create(vals_list)
        esg_report_per_type = {}
        for esg_report, root_article in zip(esg_reports, root_articles, strict=False):
            if esg_report.report_type == "csrd":
                if not (root_template := esg_report_per_type.get("csrd")):
                    root_template = self.env.ref(
                        "esg_csrd.esg_csrd_knowledge_article_template_csrd_report"
                    )
                    esg_report_per_type["csrd"] = root_template
            elif not (root_template := esg_report_per_type.get("vsme")):
                root_template = self.env.ref(
                    "esg_csrd.esg_csrd_knowledge_article_template_vsme_report"
                )
                esg_report_per_type["vsme"] = root_template
            root_article.apply_template(root_template.id)
            root_article.write({"name": esg_report.title})

            # Invite the responsible users:
            root_article.invite_members(
                esg_report.responsible_user_ids.partner_id, "write"
            )
        return esg_reports

    def write(self, vals):
        if vals.get("responsible_user_ids"):
            user_ids = [
                command[1]
                for command in vals["responsible_user_ids"]
                if command[0] == Command.LINK
            ]
            users = self.env["res.users"].browse(user_ids)
            for article in self.knowledge_article_id:
                article.invite_members(users.partner_id, "write")
        return super().write(vals)

    def action_set_to_draft(self):
        self.check_singleton()
        self.status = "draft"

    def action_set_to_done(self) -> None:
        self.check_singleton()
        self.status = "done"

    def action_edit_esg_report(self):
        self.check_singleton()
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "esg_csrd.action_esg_report_quick_create"
        )
        action["name"] = self.env._("Edit ESG Report")
        action["res_id"] = self.id
        action["context"] = {"default_report_type": self.report_type}
        return action

    def action_esg_report_pdf(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_url",
            "url": f"/esg_csrd/article/{self.knowledge_article_id.id}/esg_report?include_pdf_files=true&include_child_articles=true",
            "target": "download",
        }

    def action_update_materiality(self) -> dict:
        self.check_singleton()
        if self.report_type != "csrd":
            raise UserError(
                self.env._("You can only update the materiality of a CSRD report.")
            )
        material_metric_codes = set(
            self.env["esg.metric"]
            .search_fetch(
                domain=[
                    ("date_start", "<=", self.end_date),
                    ("date_end", ">=", self.start_date),
                    ("materiality_type", "!=", "non_material"),
                ],
                field_names=["esrs_code"],
            )
            .mapped("esrs_code")
        )
        root_article = self.knowledge_article_id
        stack = [root_article]

        while stack:
            article = stack.pop()
            fragment = html.fragment_fromstring(article.body, create_parent="div")

            is_section_updated = False
            for element in fragment.xpath("//*[@data-embedded-props]"):
                embedded_props = json_loads(element.get("data-embedded-props"))
                if esrs_code := embedded_props.get("esrs_code"):
                    embedded_props = json_loads(element.get("data-embedded-props"))
                    is_esrs_material = esrs_code in material_metric_codes

                    show_content = is_esrs_material == embedded_props.get(
                        "is_esrs_material"
                    )
                    embedded_props["showContent"] = show_content
                    element.set("data-embedded-props", json_dumps(embedded_props))
                    current_class = element.get("class", "")
                    if show_content:
                        # Remove 'd-print-none' if present
                        element.set("class", current_class.replace("d-print-none", ""))
                    # Add 'd-print-none' if not already present
                    elif "d-print-none" not in current_class:
                        element.set("class", current_class + " d-print-none")
                    is_section_updated = True

            if is_section_updated:
                elements = [
                    html.tostring(child, encoding="unicode", method="html")
                    for child in fragment.getchildren()
                ]
                article.write({"body": "".join(elements)})

            stack.extend(article.child_ids)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": self.env._(
                    "The sections of %(report_name)s have been succesfully updated with the latest materiality results.",
                    report_name=self.title,
                ),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def action_view_knowledge_report_article(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "knowledge.ir_actions_server_knowledge_home_page"
        )
        action["context"] = {"res_id": self.knowledge_article_id.id}
        return action
