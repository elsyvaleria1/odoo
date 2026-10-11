from ast import literal_eval

from odoo import api, fields, models
from odoo.fields import Command, Domain

from odoo.addons.web_studio.wizards.wizard_ir_module_module_export_customization import (
    FIELDS_TO_EXPORT,
)

PRESET_MODELS_DEFAULTS = [
    ("res.partner", {"domain": "[('user_ids', '=', False)]", "is_demo_data": True}),
    ("resource.resource", {"is_demo_data": True}),
    ("hr.employee", {"is_demo_data": True}),
    ("hr.applicant", {"is_demo_data": True}),
    ("hr.department", {"is_demo_data": True}),
    ("hr.job", {"is_demo_data": True}),
    ("hr.recruitment.stage", {}),
    ("product.public.category", {}),
    ("project.workflow.step", {}),
    ("document.document", {"domain": "[('type', '=', 'folder')]"}),
    ("product.category", {}),
    ("worksheet.template", {}),
    ("account.analytic.plan", {"is_demo_data": True}),
    ("account.analytic.account", {"is_demo_data": True}),
    ("appointment.type", {"is_demo_data": True}),
    ("project.project", {}),
    ("uom.uom", {}),
    ("resource.role", {}),
    ("product.template", {}),
    ("calendar.event", {"is_demo_data": True}),
    ("crm.tag", {"is_demo_data": True}),
    ("team.team", {"is_demo_data": True}),
    ("crm.stage", {}),
    ("crm.lead", {"is_demo_data": True}),
    ("event.event", {}),
    ("event.event.ticket", {}),
    ("event.tag", {}),
    ("event.tag.category", {}),
    ("helpdesk.ticket", {"is_demo_data": True}),
    ("product.supplierinfo", {"is_demo_data": True}),
    (
        "sale.order",
        {"domain": "[('state', 'not in', ['draft', 'cancel'])]", "is_demo_data": True},
    ),
    ("sale.order.line", {"is_demo_data": True}),
    ("loyalty.program", {"is_demo_data": True}),
    ("loyalty.reward", {"is_demo_data": True}),
    ("loyalty.rule", {"is_demo_data": True}),
    ("mail.activity", {"is_demo_data": True}),
    ("mail.activity.type", {"is_demo_data": True}),
    ("mail.template", {}),
    ("resource.kind", {}),
    ("mrp.bom", {"is_demo_data": True}),
    ("mrp.bom.line", {"is_demo_data": True}),
    ("mrp.production", {"is_demo_data": True}),
    ("mrp.routing.workcenter", {"is_demo_data": True}),
    ("mrp.workcenter", {"is_demo_data": True}),
    ("mrp.workorder", {"is_demo_data": True}),
    ("project.task", {"is_demo_data": True}),
    ("project.tags", {}),
    ("project.phase", {}),
    ("product.attribute", {}),
    ("product.attribute.value", {}),
    ("product.pricelist", {}),
    ("product.pricelist.item", {}),
    ("product.template.attribute.line", {}),
    ("product.template.attribute.value", {}),
    ("product.product", {}),
    ("product.image", {}),
    ("pos.category", {}),
    ("pos.config", {}),
    ("pos.order", {"domain": "[('state', '!=', 'cancel')]", "is_demo_data": True}),
    ("pos.order.line", {"is_demo_data": True}),
    ("pos.payment.method", {}),
    ("pos.session", {"is_demo_data": True}),
    ("pos.prep.display", {"is_demo_data": True}),
    ("sale.order.template", {}),
    ("sale.order.template.line", {}),
    ("knowledge.cover", {"include_attachment": True}),
    ("knowledge.article", {"domain": "[('category', 'in', ['workspace', 'shared'])]"}),
    ("website", {"is_demo_data": True}),
    ("website.page", {"is_demo_data": True}),
    ("website.menu", {"is_demo_data": True}),
    ("product.trace", {"is_demo_data": True}),
    ("purchase.order", {"is_demo_data": True}),
    ("purchase.order.line", {"is_demo_data": True}),
    ("quality.point", {}),
    ("quality.check", {"is_demo_data": True}),
    ("planning.slot.template", {"is_demo_data": True}),
    ("planning.recurrency", {"is_demo_data": True}),
    ("planning.slot", {"is_demo_data": True}),
    ("restaurant.floor", {}),
    ("restaurant.table", {}),
    ("repair.order", {"is_demo_data": True}),
    ("sign.item", {}),
    ("sign.request", {}),
    ("sign.template", {}),
    ("stock.quant", {"is_demo_data": True}),
    ("stock.warehouse.orderpoint", {"is_demo_data": True}),
    ("survey.survey", {"is_demo_data": True}),
    ("survey.question", {"is_demo_data": True}),
    ("survey.question.answer", {"is_demo_data": True}),
]

DEFAULTS_BY_PRESET_MODELS = {
    m[0]: {**m[1], "sequence": index} for index, m in enumerate(PRESET_MODELS_DEFAULTS)
}

DEFAULT_FIELDS_TO_EXCLUDE = {
    "res.partner": {
        "ocn_token",
        "signup_type",
        "commercial_partner_id",
        "complete_name",
        "calendar_last_notif_ack",
        "tag_ids",
        "commercial_company_name",
        "customer_rank",
        "email_normalized",
        "phone_sanitized",
        "peppol_eas",
        "peppol_endpoint",
        "contact_address_complete",
        "tz",
    },
    "hr.employee": {"employee_token", "resource_calendar_id"},
    "account.analytic.plan": {"complete_name"},
    "product.category": {"complete_name"},
    "product.product": {
        "combination_indices",
        "image_1920",
        "image_variant_128",
        "image_variant_256",
        "image_variant_512",
        "image_variant_1024",
        "base_unit_count",
    },
    "knowledge.cover": {"attachment_url"},
    "knowledge.article": {
        "root_article_id",
        "last_edition_date",
        "favorite_count",
    },
    "loyalty.rule": {
        "promo_barcode",
        "mode",
    },
    "loyalty.reward": {"description"},
    "stock.quant": {
        "inventory_date",
        "in_date",
    },
    "stock.warehouse.orderpoint": {
        "trigger",
        "name",
        "warehouse_id",
        "location_id",
    },
    "project.project": {"sale_line_id"},
    "project.task": {"triage_ids"},
    "project.workflow.step": {"project_ids"},
    "product.attribute.value": {"pav_attribute_line_ids"},
    "product.public.category": {"product_tmpl_ids"},
    "product.template.attribute.value": {
        "ptav_product_variant_ids",
        "product_tmpl_id",
        "attribute_id",
    },
    "product.template.attribute.line": {"value_count"},
    "planning.slot": {
        "access_token",
        "allocated_hours",
        "sale_order_id",
    },
    "sale.order": {
        "name",
        "team_id",
        "transaction_ids",
        "require_signature",
        "require_payment",
        "date_validity",
        "notes",
        "partner_shipping_id",
        "partner_invoice_id",
        "payment_term_id",
        "state",
        "subscription_state",
        "currency_rate",
        "amount_tax",
        "amount_untaxed",
        "amount_total",
        "amount_taxexc_to_invoice",
        "invoice_state",
    },
    "sale.order.line": {
        "invoice_line_ids",
        "task_id",
        "price_subtotal",
        "price_tax",
        "price_total",
        "price_unit_discounted_taxexc",
        "price_unit_discounted_taxinc",
        "qty_transferred_method",
        "qty_transferred",
        "qty_to_invoice",
        "qty_invoiced",
        "qty_invoiced_draft",
        "invoice_state",
        "amount_taxexc_invoiced",
        "amount_taxexc_invoiced_draft",
        "amount_taxexc_to_invoice",
    },
    "purchase.order": {
        "name",
        "origin",
        "invoice_ids",
        "reference_ids",
        "invoice_count",
        "invoice_state",
        "amount_tax",
        "amount_total",
        "currency_rate",
    },
    "purchase.order.line": {
        "currency_id",
        "move_dest_ids",
        "price_subtotal",
        "price_total",
        "price_tax",
        "qty_invoiced",
        "qty_invoiced_draft",
        "qty_transferred_method",
        "qty_transferred",
        "qty_to_invoice",
    },
    "crm.lead": {
        "recurring_plan",
        "lost_reason_id",
        "duplicate_lead_ids",
        "lang_id",
        "prorated_revenue",
        "automated_probability",
        "date_last_stage_update",
    },
    "team.team": {"member_ids"},
    "survey.survey": {"session_question_id"},
    "survey.question": {"page_id"},
}

ABSTRACT_MODEL_FIELDS_TO_EXCLUDE = {
    "mixin.html.field.history": {"html_field_history_metadata", "html_field_history"},
    "mixin.mail.activity": {"activity_ids"},
    "mixin.mail.thread": {"message_follower_ids", "message_ids", "message_partner_ids"},
    "mixin.mail.thread.blacklist": {
        "email_normalized",
        "is_blacklisted",
        "message_bounce",
    },
    "mixin.mail.alias": {"alias_id"},
    "mixin.portal": {"access_url", "access_token", "access_warning"},
    "mixin.website.published": {"website_published"},
    "mixin.avatar": {
        "avatar_1920",
        "avatar_1024",
        "avatar_512",
        "avatar_256",
        "avatar_128",
    },
    "mixin.image": {"image_1024", "image_512", "image_256", "image_128"},
}

RELATED_MODELS_TO_EXCLUDE = [
    "account.account.tag",
    "account.account",
    "account.bank.statement",
    "account.edi.document",
    "account.fiscal.position",
    "account.full.reconcile",
    "account.journal",
    "account.partial.reconcile",
    "account.payment",
    "account.root",
    "account.tax.repartition.line",
    "account.tax",
]


class StudioExportModel(models.Model):
    _name = "studio.export.model"
    _description = "Studio Export Models"
    _order = "sequence,id"
    _unique_model = models.Constraint(
        "unique(model_id)",
        "This model is already being exported.",
    )

    sequence = fields.Integer()
    model_id = fields.Many2one(
        comodel_name="ir.model",
        required=True,
        domain="[('transient', '!=', True), ('abstract', '!=', True)]",
        ondelete="cascade",
    )
    model_name = fields.Char(
        related="model_id.model",
        string="Model Name",
    )
    excluded_fields = fields.Many2many(
        comodel_name="ir.model.fields",
        string="Fields to exclude",
        compute="_compute_excluded_fields",
        store=True,
        readonly=False,
        domain="[('model_id', '=', model_id)]",
    )
    domain = fields.Text(default="[]")
    records_count = fields.Char(
        string="Records",
        compute="_compute_records_count",
    )
    is_demo_data = fields.Boolean(
        string="Demo",
        default=False,
        help="If set, the exported records will be considered as demo data during the import.",
    )
    updatable = fields.Boolean(
        default=False,
        help="Defines if the records would be updated during a module update.",
    )
    include_attachment = fields.Boolean(
        string="Attachments",
        default=False,
        help="""If set, attachments related to the exported records will be included.
        This does not include the attachments uploaded in binary fields such as pictures, files, etc.
        Include the corresponding fields in the export to get them.""",
    )

    @api.depends("model_id")
    def _compute_display_name(self):
        for record in self:
            record.display_name = record.model_id.display_name

    @api.depends("model_id")
    def _compute_excluded_fields(self) -> None:
        to_reset = self.filtered(lambda r: not r.model_id)
        to_reset.excluded_fields = None
        for record in self - to_reset:
            RecordModel = self.env[record.model_name]
            fields_not_to_export = set(
                DEFAULT_FIELDS_TO_EXCLUDE.get(record.model_name, ())
            )

            to_search = {m for m in RecordModel._base_classes__ if m._abstract}
            searched = set()
            while to_search:
                current = to_search.pop()
                if current._name in ABSTRACT_MODEL_FIELDS_TO_EXCLUDE:
                    fields_not_to_export |= ABSTRACT_MODEL_FIELDS_TO_EXCLUDE[
                        current._name
                    ]
                searched.add(current)
                to_search |= (
                    {
                        m
                        for m in current._base_classes__
                        if m not in searched and m._abstract
                    }
                    if "_base_classes__" in dir(current)
                    else set()
                )

            for field_name, field in RecordModel._fields.items():
                if field_name in fields_not_to_export:
                    continue
                module = field._modules[0] if field._modules else None
                if (
                    (
                        (field.compute and not field.related)
                        and not (field.store or field.inverse)
                    )
                    or (
                        field.related
                        and (
                            field.related_field.model_name in RELATED_MODELS_TO_EXCLUDE
                            or not ((field.store and field.readonly) or field.required)
                        )
                    )
                    or (field.type == "one2many")
                    or (module and module.startswith("l10n_"))
                    or (
                        field.type in ["many2one", "many2many"]
                        and field.comodel_name in RELATED_MODELS_TO_EXCLUDE
                    )
                ):
                    fields_not_to_export.add(field_name)

            if RecordModel._parent_store:
                fields_not_to_export.add("parent_path")

            fields_not_to_export -= set(FIELDS_TO_EXPORT.get(record.model_name, []))
            excluded_fields = self.env["ir.model.fields"].search(
                [
                    ("model_id", "=", record.model_id.id),
                    ("name", "in", list(fields_not_to_export)),
                ]
            )
            record.excluded_fields = [Command.set(excluded_fields.ids)]

    @api.depends("model_name", "domain")
    def _compute_records_count(self) -> None:
        for record in self:
            records_count = (
                self.env[record.model_name]
                .sudo()
                .search_count(literal_eval(record.domain or "[]"))
            )
            record.records_count = self.env._("%s record(s)", records_count)

    def action_preset(self) -> None:
        curr_models_names = [
            r["model_name"] for r in self.search_read([], ["model_name"])
        ]
        preset_models = [
            (model, DEFAULTS_BY_PRESET_MODELS.get(model["model"], {}))
            for model in self.env["ir.model"].search_read(
                Domain("transient", "=", False)
                & Domain("abstract", "=", False)
                & (
                    Domain("model", "in", list(DEFAULTS_BY_PRESET_MODELS.keys()))
                    | Domain("model", "=like", r"x\_%")
                    | Domain("state", "=", "manual")
                ),
                ["model"],
            )
        ]
        to_create = [
            {**defaults, "model_id": model["id"]}
            for model, defaults in preset_models
            if model["model"] not in curr_models_names
            and (
                not self.env[model["model"]]._log_access
                or (
                    self.env[model["model"]]
                    .sudo()
                    .search_count(literal_eval(defaults.get("domain", "[]")))
                )
            )
        ]

        if to_create:
            self.create(to_create)

    def _get_exportable_records(self):
        self.check_singleton()
        domain = literal_eval(self.domain or "[]")
        model = self.env[self.model_name].sudo()
        return model.search(domain)
