from collections import OrderedDict

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import groupby, topological_sort
from odoo.tools.misc import OrderedSet

DEFAULT_MODELS_TO_EXPORT = [
    "res.groups",
    "res.groups.privilege",
    "ir.module.category",
    "report.paperformat",
    "ir.model",
    "ir.model.fields",
    "ir.ui.view",
    "ir.actions.act_window",
    "ir.actions.act_window.view",
    "ir.actions.report",
    "mail.template",
    "ir.actions.server",
    "ir.ui.menu",
    "ir.filters",
    "automation.rule",
    "ir.access",
    "ir.default",
    "approval.category",
    "approval.category.step",
    "approval.category.step.member",
    "approval.binding",
]

FIELDS_TO_EXPORT = {
    "automation.rule": [
        "action_server_ids",
        "active",
        "description",
        "filter_domain",
        "filter_pre_domain",
        "last_run",
        "log_webhook_calls",
        "model_id",
        "name",
        "on_change_field_ids",
        "record_getter",
        "trg_date_id",
        "trg_date_range_type",
        "trg_date_range",
        "trg_field_ref",
        "trg_selection_field_id",
        "trigger_field_ids",
        "trigger",
    ],
    "ir.actions.act_window": [
        "binding_model_id",
        "binding_type",
        "binding_view_types",
        "context",
        "domain",
        "filter",
        "group_ids",
        "help",
        "limit",
        "name",
        "res_model",
        "search_view_id",
        "target",
        "type",
        "usage",
        "view_id",
        "view_mode",
    ],
    "ir.actions.act_window.view": [
        "act_window_id",
        "multi",
        "sequence",
        "view_id",
        "view_mode",
    ],
    "ir.actions.report": [
        "attachment",
        "attachment_use",
        "binding_model_id",
        "binding_type",
        "binding_view_types",
        "group_ids",
        "model",
        "multi",
        "name",
        "paperformat_id",
        "report_name",
        "report_type",
    ],
    "ir.actions.server": [
        "binding_model_id",
        "binding_type",
        "binding_view_types",
        "child_ids",
        "code",
        "crud_model_id",
        "evaluation_type",
        "group_ids",
        "help",
        "link_field_id",
        "model_id",
        "name",
        "resource_ref",
        "selection_value",
        "sequence",
        "state",
        "update_boolean_value",
        "update_field_id",
        "update_m2m_operation",
        "update_path",
        "usage",
        "value",
        "webhook_field_ids",
        "webhook_url",
    ],
    "ir.filters": [
        "action_id",
        "active",
        "context",
        "domain",
        "is_default",
        "model_id",
        "name",
        "sort",
    ],
    "ir.model": [
        "info",
        "is_mail_thread",
        "is_mail_activity",
        "model",
        "name",
        "state",
        "transient",
    ],
    "ir.access": [
        "active",
        "anchor",
        "class_id",
        "domain",
        "exempt_group_ids",
        "group_id",
        "guard_scope",
        "kind",
        "model_id",
        "name",
        "operation",
        "predicate_args",
        "predicate_id",
        "reach",
        "verbs",
    ],
    "ir.model.fields": [
        "compute",
        "copied",
        "depends",
        "domain",
        "field_description",
        "groups",
        "group_expand",
        "help",
        "index",
        "model",
        "model_id",
        "name",
        "on_delete",
        "readonly",
        "related",
        "relation",
        "relation_field",
        "relation_table",
        "required",
        "selectable",
        "selection",
        "size",
        "state",
        "store",
        "tracking",
        "translate",
        "ttype",
        "currency_field",
    ],
    "ir.ui.menu": [
        "action",
        "active",
        "group_ids",
        "name",
        "parent_id",
        "sequence",
        "web_icon",
        "web_icon_data",
    ],
    "ir.ui.view": [
        "active",
        "arch",
        "group_ids",
        "inherit_id",
        "key",
        "mode",
        "model",
        "name",
        "priority",
        "type",
        "website_id",
    ],
    "mail.template": [
        "auto_delete",
        "body_html",
        "email_cc",
        "email_from",
        "email_to",
        "lang",
        "model_id",
        "name",
        "partner_to",
        "ref_ir_act_window",
        "reply_to",
        "report_template_ids",
        "scheduled_date",
        "subject",
        "use_default_to",
    ],
    "res.groups": [
        "sequence",
        "privilege_id",
        "comment",
        "implied_ids",
        "name",
        "share",
    ],
    "res.groups.privilege": ["sequence", "category_id", "name", "placeholder"],
    "ir.module.category": ["sequence", "name"],
    "ir.default": ["field_id", "condition", "json_value"],
    "approval.category": [
        "name",
        "sequence_code",
        "notify_sequentially",
        "approval_minimum",
        "allow_self_approval",
    ],
    "approval.category.step": [
        "category_id",
        "name",
        "sequence",
        "active",
        "minimum",
        "currency_id",
        "group_id",
        "exclusive",
        "notify_user_ids",
        "subject_model_id",
        "subject_domain",
    ],
    "approval.category.step.member": [
        "step_id",
        "user_id",
        "date_end",
        "delegated_by_id",
    ],
    "approval.binding": [
        "model_id",
        "method",
        "action_id",
        "category_id",
        "mode",
        "sudo_policy",
        "approve_on_invoke",
        "run_on_approval",
        "subject_domain",
        "reset_domain",
        "sequence",
        "active",
    ],
    "ir.attachment": [
        "name",
        "type",
        "datas",
        "url",
        "res_id",
        "res_model",
        "res_field",
        "access_token",
        "key",
        "website_id",
    ],
    "mail.message": [
        "subject",
        "res_id",
        "model",
        "body",
        "message_type",
        "subtype_id",
        "author_id",
        "attachment_ids",
    ],
}

MODELS_WITH_NOUPDATE = [
    "ir.attachment",
    "ir.access",
]

RELATIONS_NOT_TO_EXPORT = {
    "automation.rule": ["trg_date_calendar_id"],
    "ir.actions.server": ["partner_ids"],
    "ir.filters": ["user_ids"],
    "mail.template": ["attachment_ids", "mail_server_id"],
    "report.paperformat": ["report_ids"],
    "res.groups": ["user_ids"],
}


def _find_circular_dependencies(elems):
    circular_dependencies = []

    def traverse(elem, visited, stack):
        visited.add(elem)
        stack.append(elem)

        if elem in elems:
            for dependency in elems[elem]:
                if dependency == elem:
                    continue
                if dependency not in visited and not traverse(
                    dependency, visited, stack
                ):
                    return False
                if dependency == stack[0]:
                    stack.append(dependency)
                    circular_dependencies.append(stack.copy())
                    return False

        stack.remove(elem)
        return True

    to_skip = set()
    for element in elems:
        if element not in to_skip and not traverse(element, set(), []):
            to_skip.update(circular_dependencies[-1])

    return circular_dependencies


def _get_attachment_fields(env, model) -> list:
    def is_attachment_field(info) -> bool:
        return "relation" in info and info["relation"] == "ir.attachment"

    Model = env[model]
    return [f for f in Model.fields_get().items() if is_attachment_field(f[1])]


class WizardIrModuleModuleExportCustomization(models.TransientModel):
    _name = "wizard.ir.module.module.export.customization"
    _description = "Studio Export Wizard"

    def _default_studio_export_data(self):
        data = self.env["ir.model.data"].search(
            [
                ("studio", "=", True),
                ("model", "in", DEFAULT_MODELS_TO_EXPORT),
            ]
        )

        active_ids = {}
        for model_name, model_data_list in groupby(data, lambda d: d.model):
            records = self.env[model_name].browse(d.res_id for d in model_data_list)
            if records._active_name:
                records = records.filtered(records._active_name)
            active_ids[model_name] = set(records.ids)

        active_data = [d for d in data if d.res_id in active_ids[d.model]]

        return self.env["wizard.ir.module.module.export.customization.line"].create(
            [
                {"model": d.model, "res_id": d.res_id, "studio": d.studio}
                for d in active_data
            ]
        )

    default_export_data = fields.Many2many(
        comodel_name="wizard.ir.module.module.export.customization.line",
        relation="rel_studio_export_wizard_data",
        default=lambda self: self._default_studio_export_data(),
    )

    include_additional_data = fields.Boolean(
        string="Include Data",
        default=False,
    )
    include_demo_data = fields.Boolean(default=False)

    additional_models = fields.Many2many(
        comodel_name="studio.export.model",
        string="Additional models to export",
        compute="_compute_additional_models",
        help="Additional models you may choose to export in addition to the Studio customizations",
    )
    additional_export_data = fields.Many2many(
        comodel_name="wizard.ir.module.module.export.customization.line",
        relation="rel_studio_export_wizard_additional_data",
        compute="_compute_export_data",
    )

    @api.constrains("default_export_data")
    def _check_export_data(self) -> None:
        for rec in self:
            data = rec.default_export_data | rec.additional_export_data
            for model, records in data.grouped("model").items():
                if len(records) != len(set(records.mapped("res_id"))):
                    raise ValidationError(
                        self.env._(
                            "Model '%s' should not contain records with the same ID.",
                            model,
                        )
                    )

    @api.depends("include_additional_data", "include_demo_data")
    def _compute_additional_models(self) -> None:
        to_update = self.filtered("include_additional_data")
        (self - to_update).additional_models = False
        for record in to_update:
            domain = (
                [("is_demo_data", "=", False)] if not record.include_demo_data else []
            )
            record.additional_models = self.env["studio.export.model"].search(domain)

    @api.depends("additional_models", "default_export_data")
    def _compute_export_data(self) -> None:
        to_update = self.filtered("additional_models")
        (self - to_update).additional_export_data = False
        for rec in to_update:
            rec.additional_export_data = self.env[
                "wizard.ir.module.module.export.customization.line"
            ].create(rec._prepare_additional_export_data_vals())

    def _prepare_additional_export_data_vals(self):
        self.check_singleton()
        export_data_vals = []

        def add(export_model, model, records, pre=False, post=False):
            nonlocal export_data_vals
            model_default_data_ids = self.default_export_data.filtered(
                lambda r: r.model == model
            ).mapped("res_id")

            model_default_data_ids += [
                export_data["res_id"]
                for export_data in export_data_vals
                if export_data["model"] == model
            ]

            export_data_vals += [
                {
                    "model": model,
                    "res_id": res_id,
                    "is_demo_data": export_model.is_demo_data,
                    "pre": pre,
                    "post": post,
                }
                for res_id in records.ids
                if res_id not in model_default_data_ids
            ]

        for export_model in self.additional_models.sorted("sequence"):
            to_export = export_model._get_exportable_records()
            if to_export is None:
                continue
            add(export_model, export_model.model_name, to_export)

            if export_model.model_name == "website":
                attachments = self.env["ir.attachment"].search(
                    [
                        ("type", "=", "binary"),
                        ("website_id", "in", to_export.ids),
                        "!",
                        ("name", "=like", "%.js.map"),
                        "!",
                        ("name", "=like", "%.css.map"),
                        (
                            "mimetype",
                            "not in",
                            ["application/javascript", "text/css", "text/plain"],
                        ),
                    ]
                )
                add(export_model, "ir.attachment", attachments, post=True)

                website_views = self.env["ir.ui.view"].search(
                    [
                        ("website_id", "in", to_export.ids),
                        ("arch_updated", "=", True),
                    ]
                )
                add(export_model, "ir.ui.view", website_views)

            if export_model.model_name == "worksheet.template":
                model_data = to_export.model_id
                add(export_model, "ir.model", model_data)

                model_access_data = self.env["ir.access"].search(
                    [("model_id", "in", to_export.model_id.ids)]
                )
                add(export_model, "ir.access", model_access_data)

                add(export_model, "res.groups", model_access_data.group_id)

                view_data = self.env["ir.ui.view"].search(
                    [("model", "in", to_export.model_id.mapped("model"))]
                )
                add(export_model, "ir.ui.view", view_data)

                action_data = to_export.action_id
                add(export_model, "ir.actions.act_window", action_data)

                field_data = to_export.model_id.field_id.filtered_domain(
                    [("state", "!=", "base")]
                )
                add(export_model, "ir.model.fields", field_data)

            if export_model.model_name == "project.workflow.step":
                mail_templates = to_export.mail_template_id
                add(export_model, "mail.template", mail_templates)

            if export_model.include_attachment:
                fields = _get_attachment_fields(self.env, export_model.model_name)
                pre_attachments = self.env["ir.attachment"].search(
                    [
                        ("res_id", "in", to_export.ids),
                        ("res_model", "=", export_model.model_name),
                        "|",
                        (
                            "res_field",
                            "in",
                            [f[0] for f in fields if f[1]["type"] != "one2many"],
                        ),
                        ("res_field", "=", False),
                    ]
                )
                add(export_model, "ir.attachment", pre_attachments, pre=True)
                other_attachments = self.env["ir.attachment"].search(
                    [
                        ("res_id", "in", to_export.ids),
                        ("res_model", "=", export_model.model_name),
                        (
                            "res_field",
                            "in",
                            [f[0] for f in fields if f[1]["type"] == "one2many"],
                        ),
                    ]
                )
                add(export_model, "ir.attachment", other_attachments, post=True)
        return export_data_vals

    def get_export_info(self) -> tuple:
        self.check_singleton()
        all_data = self.default_export_data | self.additional_export_data
        no_update_models = MODELS_WITH_NOUPDATE + self.additional_models.filtered(
            lambda r: not r.updatable
        ).mapped("model_name")
        pre_export = []
        export = []
        post_export = []

        def add(
            info,
            model,
            fields_by_group,
            real_records,
            records_data,
            suffix="",
            force_exclude=(),
        ):
            if not records_data:
                return

            res_ids = records_data.mapped("res_id")
            records = real_records.filtered(lambda r: r.id in res_ids)

            for group, group_fields in fields_by_group.items():
                for field_to_exclude in force_exclude:
                    if field_to_exclude in group_fields:
                        group_fields.remove(field_to_exclude)

                if not group_fields:
                    continue

                path_info = (group, suffix)
                no_update = model in no_update_models
                info.append((model, records, group_fields, no_update, path_info))

        models_to_export, circular_dependencies = self._get_models_to_export()
        for model, _is_demo, fields_by_group, data, real_records in models_to_export:
            pre_records = data.filtered("pre")
            post_records = data.filtered("post")
            data_records = data - pre_records - post_records

            force_exclude = (
                ["res_id", "res_model", "res_field", "website_id"]
                if model == "ir.attachment"
                else []
            )
            add(
                pre_export,
                model,
                fields_by_group,
                real_records,
                pre_records,
                suffix="_pre",
                force_exclude=force_exclude,
            )
            add(export, model, fields_by_group, real_records, data_records)
            add(
                post_export,
                model,
                fields_by_group,
                real_records,
                post_records,
                suffix="_post",
            )

        return all_data, pre_export + export + post_export, circular_dependencies

    def _get_fields_to_export_by_models(self):
        self.check_singleton()
        all_data = self.default_export_data | self.additional_export_data
        model_names = set(all_data.mapped("model"))
        additional_models_by_name = self.additional_models.grouped("model_name")
        result = {}
        for model_name in model_names:
            Model = self.env[model_name]
            fields_to_export = [
                field
                for field in FIELDS_TO_EXPORT.get(model_name, [])
                if field in Model._fields
            ]

            if not fields_to_export:
                fields_to_export = list(
                    OrderedSet(Model._fields.keys()) - OrderedSet(models.MAGIC_COLUMNS)
                )

            if RELATIONS_NOT_TO_EXPORT.get(model_name):
                fields_to_export = list(
                    OrderedSet(fields_to_export)
                    - OrderedSet(RELATIONS_NOT_TO_EXPORT.get(model_name))
                )

            export_model = additional_models_by_name.get(
                model_name, self.additional_models.browse()
            )
            export_model_fields_to_exclude = export_model.excluded_fields.mapped("name")
            fields_to_export = [
                f for f in fields_to_export if f not in export_model_fields_to_exclude
            ]

            fields_details = Model.fields_get(fields_to_export)
            field_deps = OrderedDict.fromkeys(fields_to_export)
            for field in fields_to_export:
                field_deps[field] = (
                    [f.split(".")[0] for f in fields_details[field]["depends"]]
                    if field in fields_details
                    else []
                )

            result[model_name] = topological_sort(field_deps, strict=False)

        return result

    def _get_models_to_export(self) -> tuple:
        self.check_singleton()
        fields_by_models = self._get_fields_to_export_by_models()
        result = []
        circular_dependencies = []
        all_data = self.default_export_data | self.additional_export_data

        data_by_is_demo = all_data.grouped("is_demo_data")
        for is_demo in [True, False]:
            data = data_by_is_demo.get(is_demo, all_data.browse())
            data_by_model = data.grouped("model")
            current_models = set(data.mapped("model"))
            model_names = [m for m in DEFAULT_MODELS_TO_EXPORT if m in current_models]
            model_names += sorted([m for m in current_models if m not in model_names])

            demo_records = {m: records for (m, demo, _, _, records) in result if demo}

            model_grouped_fields = {}
            model_data = {}
            model_records = {}
            for model in model_names:
                model_grouped_fields[model] = self._get_fields_groups(
                    model, is_demo, fields_by_models[model], demo_records
                )
                model_data[model] = data_by_model.get(model, data.browse())
                sudo_model = self.env[model].sudo()
                model_records[model] = sudo_model.browse(
                    model_data[model].mapped("res_id")
                )

            models_deps = OrderedDict().fromkeys(model_names)
            for model in model_names:
                models_deps[model] = set()
                for field_name, info in sorted(
                    self.env[model].fields_get().items(), key=lambda item: item[0]
                ):
                    if (
                        field_name
                        not in model_grouped_fields[model][
                            "demo" if is_demo else "data"
                        ]
                        or "relation" not in info
                        or info["type"] == "one2many"
                    ):
                        continue

                    related_model = info.get("relation")
                    if related_model not in model_records:
                        continue
                    related_ids = set(model_records[related_model].ids)
                    if any(
                        related_ids.intersection(record[field_name].ids)
                        for record in model_records[model]
                    ):
                        models_deps[model].add(related_model)

            circular_dependencies.extend(
                (is_demo, circular_dependency)
                for circular_dependency in _find_circular_dependencies(models_deps)
            )
            result.extend(
                (
                    model,
                    is_demo,
                    model_grouped_fields[model],
                    model_data[model],
                    model_records[model],
                )
                for model in topological_sort(models_deps, strict=False)
            )

        return result, circular_dependencies

    def _get_fields_groups(
        self, model, is_demo, fields_to_export, demo_records
    ) -> dict:
        self.check_singleton()

        if is_demo:
            return {"demo": fields_to_export}

        all_data = self.default_export_data | self.additional_export_data

        fields_relations = {
            field_name: field_info["relation"]
            for (field_name, field_info) in self.env[model]
            .fields_get(fields_to_export)
            .items()
            if field_info.get("relation") and field_info["relation"] != model
        }
        demo_fields_to_export = []
        new_fields_to_export = []
        for field_name in fields_to_export:
            related_model = fields_relations.get(field_name)
            if related_model in demo_records:
                data = all_data.filtered(
                    lambda r: r.model == model and not r.is_demo_data
                )
                records = self.env[model].sudo().browse(data.mapped("res_id"))
                if any(r[field_name] in demo_records[related_model] for r in records):
                    demo_fields_to_export.append(field_name)
                    continue
            new_fields_to_export.append(field_name)

        return {"data": new_fields_to_export, "demo": demo_fields_to_export}

    @api.onchange("include_additional_data")
    def _onchange_include_additional_data(self) -> None:
        if not self.include_additional_data:
            self.include_demo_data = False

    @api.onchange("include_demo_data")
    def _onchange_include_demo_data(self) -> None:
        if self.include_demo_data:
            self.include_additional_data = True
