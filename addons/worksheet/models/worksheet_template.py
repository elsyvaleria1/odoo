import collections
import dataclasses
import re
from collections import defaultdict
from collections.abc import Callable

from lxml import etree

from odoo import Command, api, fields, models
from odoo.db.schema import add_constraint
from odoo.exceptions import UserError, ValidationError
from odoo.libs.sql import normalize_identifier

from odoo.addons.base.models.ir_model_common import MODULE_UNINSTALL_FLAG


@dataclasses.dataclass(frozen=True, kw_only=True)
class WorksheetModelHooks:
    module: str
    user_group: str
    manager_group: str
    access_all_groups: tuple[str, ...]
    template_fields: Callable[[], list] | None = None
    form_arch: Callable[[], str] | None = None
    list_arch: Callable[[], str] | None = None
    search_arch: Callable[[], str] | None = None
    additional_access_vals_list: Callable[[str, int], list[dict]] | None = None


class WorksheetTemplate(models.Model):
    _name = "worksheet.template"
    _description = "Worksheet Template"
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer()
    worksheet_count = fields.Integer(
        compute="_compute_worksheet_count",
        compute_sudo=True,
    )
    model_id = fields.Many2one(
        comodel_name="ir.model",
        readonly=True,
        domain=[("state", "=", "manual")],
    )
    action_id = fields.Many2one(
        comodel_name="ir.actions.act_window",
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        domain=lambda self: [("id", "in", self.env.companies.ids)],
    )
    report_view_id = fields.Many2one(
        comodel_name="ir.ui.view",
        copy=False,
        readonly=True,
        domain=[("type", "=", "qweb")],
    )
    active = fields.Boolean(default=True)
    res_model = fields.Char(
        string="Host Model",
        help="The model that is using this template",
    )

    def _compute_worksheet_count(self) -> None:
        for record in self:
            record.worksheet_count = (
                record.model_id and self.env[record.model_id.model].search_count([])
            ) or 0

    @api.constrains("report_view_id", "model_id")
    def _check_report_view_type(self) -> None:
        for worksheet_template in self:
            if worksheet_template.model_id and worksheet_template.report_view_id:
                if worksheet_template.report_view_id.type != "qweb":
                    raise ValidationError(
                        self.env._(
                            "The template to print this worksheet template should be a QWeb template."
                        )
                    )

    @api.constrains("res_model")
    def _check_res_model_exists(self) -> None:
        res_models = self.mapped("res_model")
        ir_model_names = [
            res["model"]
            for res in self.env["ir.model"]
            .sudo()
            .search_read([("model", "in", res_models)], ["model"])
        ]
        if any(model_name not in ir_model_names for model_name in res_models):
            raise ValidationError(
                self.env._("The host model name should be an existing model.")
            )

    @api.model_create_multi
    def create(self, vals_list):
        templates = super().create(vals_list)
        if not self.env.context.get("worksheet_no_generation"):
            for template in templates:
                template._create_worksheet_model()
        return templates

    def write(self, vals):
        old_company_id = self.company_id
        res = super().write(vals)
        if "company_id" in vals and self.company_id:
            update_company_id = old_company_id - self.company_id
            template_dict = defaultdict(lambda: self.env["worksheet.template"])
            for template in self:
                template_dict[template.res_model] |= template
            for res_model, templates in template_dict.items():
                for model, _name in self._get_models_to_check_dict()[res_model]:
                    records = self.env[model].search(
                        [("worksheet_template_id", "in", templates.ids)]
                    )
                    for record in records:
                        if (
                            record.company_id
                            not in record.worksheet_template_id.company_id
                        ):
                            if update_company_id:
                                company_name = update_company_id.mapped("name")
                                raise UserError(
                                    self.env._(
                                        "Unfortunately, you cannot unlink this worksheet template from %s because the template is still connected to tasks within the company.",
                                        company_name,
                                    )
                                )
                            company_name = (
                                record.worksheet_template_id.company_id.mapped("name")
                            )
                            raise UserError(
                                self.env._(
                                    "You can't restrict this worksheet template to '%(selected_company)s' because it's still connected to tasks in '%(tasks_company)s' (and potentially other companies). Please either unlink those tasks from this worksheet template, "
                                    "move them to a project for the right company, or keep this worksheet template open to all companies.",
                                    selected_company=company_name,
                                    tasks_company=record.company_id.name,
                                )
                            )
        return res

    def unlink(self):
        if self.env.context.get(MODULE_UNINSTALL_FLAG):
            return super().unlink()

        models_ids = self.mapped("model_id.id")
        self.env["ir.ui.view"].search(
            [("model", "in", self.mapped("model_id.model"))]
        ).unlink()
        self.mapped("report_view_id").unlink()
        self.env["ir.access"].search([("model_id", "in", models_ids)]).unlink()
        x_name_fields = self.env["ir.model.fields"].search(
            [("model_id", "in", models_ids), ("name", "=", "x_name")]
        )
        x_name_fields.write(
            {"related": False}
        )
        self.mapped("action_id").unlink()
        self.mapped("model_id").with_context(**{MODULE_UNINSTALL_FLAG: True}).unlink()

        return super(WorksheetTemplate, self.exists()).unlink()

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        return [
            dict(
                vals,
                name=self.env._("%s (copy)", template.name),
                model_id=False,
            )
            for template, vals in zip(self, vals_list, strict=False)
        ]

    def copy(self, default=None):
        templates = super(
            WorksheetTemplate, self.with_context(worksheet_no_generation=True)
        ).copy(default)
        for template in templates:
            template._create_worksheet_model()
        return templates

    def _create_worksheet_model(self) -> None:
        self.check_singleton()
        res_model = self.res_model.replace(".", "_")
        name = "x_%s_worksheet_template_%d" % (res_model, self.id)

        hooks = self._get_worksheet_hooks()
        user_group = self.env.ref(hooks.user_group)

        self.env.flush_all()

        module_name = hooks.module
        xid_values = []
        model_counter = collections.Counter()

        def register_xids(records):
            for record in records:
                model_counter[record._name] += 1
                xid_values.append(
                    {
                        "name": "{}_{}_{}".format(
                            name,
                            record._name.replace(".", "_"),
                            model_counter[record._name],
                        ),
                        "module": module_name,
                        "model": record._name,
                        "res_id": record.id,
                        "noupdate": True,
                    }
                )
            return records

        model = register_xids(
            self.env["ir.model"]
            .sudo()
            .create(
                {
                    "name": self.name,
                    "model": name,
                    "field_id": self._prepare_default_fields_values()
                    + [
                        Command.create(
                            {
                                "name": "x_name",
                                "field_description": "Name",
                                "ttype": "char",
                                "related": "x_%s_id.name" % res_model,
                            }
                        ),
                    ],
                }
            )
        )
        if self.env.context.get("install_module"):
            x_name_field = model.field_id.filtered(lambda f: f.name == "x_name")
            self.env["ir.model.data"].sudo().create(
                {
                    "name": f"{model.model}_field_x_name",
                    "model": "ir.model.fields",
                    "module": self.env.context.get("install_module"),
                    "res_id": x_name_field.id,
                    "noupdate": True,
                }
            )

        register_xids(sorted(model.field_id, key=lambda field: field.name))

        additional_access_vals_list = (
            hooks.additional_access_vals_list(name, model.id)
            if hooks.additional_access_vals_list
            else []
        )
        register_xids(
            self.env["ir.access"]
            .sudo()
            .create(
                [
                    {
                        "name": name + "_manager_access",
                        "model_id": model.id,
                        "group_id": self.env.ref(hooks.manager_group).id,
                        "kind": "permission",
                        "operation": "crud",
                    },
                    {
                        "name": name + "_own",
                        "model_id": model.id,
                        "group_id": user_group.id,
                        "kind": "permission",
                        "operation": "crud",
                        "domain": "[('create_uid', '=', user.id)]",
                    },
                    *(
                        {
                            "name": name + "_all",
                            "model_id": model.id,
                            "group_id": self.env.ref(xmlid).id,
                            "kind": "permission",
                            "operation": "crud",
                        }
                        for xmlid in hooks.access_all_groups
                    ),
                    *additional_access_vals_list,
                ]
            )
        )

        __, __, search_view = register_xids(
            self.env["ir.ui.view"]
            .sudo()
            .create(
                [
                    self._prepare_default_form_view_values(model),
                    self._prepare_default_list_view_values(model),
                    self._prepare_default_search_view_values(model),
                ]
            )
        )
        action = register_xids(
            self.env["ir.actions.act_window"]
            .sudo()
            .create(
                {
                    "name": "Worksheets",
                    "res_model": model.model,
                    "search_view_id": search_view.id,
                    "context": self._get_template_action_context(),
                }
            )
        )

        self.env["ir.model.data"].sudo().create(xid_values)

        self.write(
            {
                "action_id": action.id,
                "model_id": model.id,
            }
        )
        self.sudo()._create_qweb_report_template()

        conname = normalize_identifier(f"{name}_x_{res_model}_id_uniq")
        concode = "unique(x_%s_id)" % (res_model)
        add_constraint(self.env.cr, name, conname, concode)

    def _get_template_action_context(self):
        return {
            "edit": False,
            "create": False,
            "delete": False,
            "duplicate": False,
        }

    def _prepare_default_fields_values(self):
        res_model_name = self.res_model.replace(".", "_")
        hooks = self._get_worksheet_model_hooks().get(self.res_model)
        fields_func = hooks and hooks.template_fields
        return [
            Command.create(
                {
                    "name": "x_%s_id" % (res_model_name),
                    "field_description": self.env[self.res_model]._description,
                    "ttype": "many2one",
                    "relation": self.res_model,
                    "required": True,
                    "on_delete": "cascade",
                }
            ),
            Command.create(
                {
                    "name": "x_comments",
                    "ttype": "html",
                    "field_description": "Comments",
                }
            ),
        ] + ((fields_func and fields_func()) or [])

    def _prepare_default_form_view_values(self, model) -> dict:
        res_model_name = self.res_model.replace(".", "_")
        hooks = self._get_worksheet_model_hooks().get(self.res_model)
        form_arch_func = hooks and hooks.form_arch
        return {
            "type": "form",
            "name": "template_view_" + "_".join(self.name.split(" ")),
            "model": model.model,
            "arch": (form_arch_func and form_arch_func())
            or """
                <form create="false" duplicate="false">
                    <sheet>
                        <h1 invisible="context.get('studio') or context.get('default_x_%s_id')">
                            <field name="x_%s_id"/>
                        </h1>
                        <group>
                            <field name="x_comments" placeholder="Add details about your intervention..."/>
                        </group>
                    </sheet>
                </form>
            """
            % (res_model_name, res_model_name),
        }

    def _prepare_default_list_view_values(self, model) -> dict:
        hooks = self._get_worksheet_model_hooks().get(self.res_model)
        tree_arch_func = hooks and hooks.list_arch
        return {
            "type": "list",
            "name": "list_view_" + self.name.replace(" ", "_"),
            "model": model.model,
            "arch": (tree_arch_func and tree_arch_func())
            or """
                <list default_order="create_date DESC">
                    <field name="create_date"/>
                    <field name="x_name"/>
                </list>
            """,
        }

    def _prepare_default_search_view_values(self, model) -> dict:
        hooks = self._get_worksheet_model_hooks().get(self.res_model)
        search_arch_func = hooks and hooks.search_arch
        return {
            "type": "search",
            "name": "search_view_" + self.name.replace(" ", "_"),
            "model": model.model,
            "arch": (search_arch_func and search_arch_func())
            or """
                <search>
                    <field name="x_name"/>
                    <filter string="Created on" date="create_date" name="create_date"/>
                    <filter name="group_by_month" string="Created on" context="{'group_by': 'create_date:month'}"/>
                </search>
            """,
        }

    @api.model
    def _get_worksheet_model_hooks(self) -> dict[str, WorksheetModelHooks]:
        return {}

    def _get_worksheet_hooks(self) -> WorksheetModelHooks:
        self.check_singleton()
        hooks = self._get_worksheet_model_hooks().get(self.res_model)
        if hooks is None:
            raise NotImplementedError(
                f"No worksheet hooks registered for {self.res_model}"
            )
        return hooks

    @api.model
    def _get_models_to_check_dict(self):
        return {}

    def action_analysis_report(self):
        self.check_singleton()
        return {
            "name": self.env._("Analysis"),
            "type": "ir.actions.act_window",
            "view_mode": "graph,pivot,list,form",
            "res_model": self.sudo().model_id.model,
            "context": "{'search_default_group_by_month': True}",
            "help": """
                <p class="o_view_nocontent_empty_folder">%s</p>
                <p>%s</p>
                """
            % (
                self.env._("No data to display"),
                self.env._(
                    "Keep track of and analyze intervention data. Identify recurring patterns and take preventive measures accordingly."
                ),
            ),
        }

    def action_view_worksheets(self):
        action = self.action_id.sudo().read()[0]
        action["context"] = dict(
            self.env["ir.actions.actions"]._eval_action_context(
                action.get("context", "{}")
            ),
            search_default_group_by_month=True,
        )
        if self.worksheet_count == 1:
            action.update(
                {
                    "views": [(False, "form")],
                    "res_id": self.env[action["res_model"]].search([], limit=1).id,
                }
            )
        return action


    def get_x_model_form_action(self):
        action = self.action_id.read()[0]
        action.update(
            {
                "views": [[False, "form"]],
                "context": {
                    "default_x_%s_id" % self.res_model.replace(".", "_"): True
                },
            }
        )
        return action

    def _get_fields_qweb_arch_omitted(self) -> list:
        return [
            "x_%s_id" % self.res_model.replace(".", "_"),
            "x_name",
        ]

    def _add_field_node_to_container(self, field_node, form_view_fields, container_col):
        field_name = field_node.attrib["name"]
        invisible = field_node.get("invisible", "False")
        if invisible in ("True", "1"):
            return container_col

        new_container_col = container_col
        if field_name not in self._get_fields_qweb_arch_omitted():
            field_info = form_view_fields.get(field_name)
            widget = field_node.attrib.get("widget", False)
            is_signature = False
            if widget:
                if widget == "signature":
                    is_signature = True
                    field_node.attrib.pop("widget")
                elif widget == "image":
                    field_node.attrib["t-options-widget"] = "'image'"
                    field_node.attrib["t-options-qweb_img_raw_data"] = "1"
            if field_info:
                field_name = "worksheet." + field_node.attrib["name"]
                field_node.attrib.pop("name")
                if is_signature:
                    field_node.tag = "img"
                    field_node.attrib["style"] = "width: 250px;"
                    field_node.attrib["t-att-src"] = "image_data_uri(%s)" % field_name
                    field_node.attrib["t-if"] = field_name
                elif field_info.get("type") == "boolean":
                    field_node.tag = "i"
                    field_node.attrib["t-att-class"] = (
                        "'col-lg-7 col-12 fa ' + ('fa-check-square' if %s else 'fa-square-o')"
                        % field_name
                    )
                elif field_node.attrib.get("filename"):
                    field_node.tag = "div"
                    field_node.attrib["t-att-class"] = (
                        "'col-7' if report_type == 'pdf' else 'col-lg-7 col-12'"
                    )
                    field_node.attrib["t-field"] = "worksheet." + field_node.attrib.get(
                        "filename"
                    )
                else:
                    field_node.tag = "div"
                    field_node.attrib["t-att-class"] = (
                        "'col-7' if report_type == 'pdf' else 'col-lg-9 col-12'"
                    )
                    field_node.attrib["t-field"] = field_name
                description = etree.Element(
                    "div",
                    {
                        "t-att-class": "('col-5' if report_type == 'pdf' else 'col-lg-3 col-12') + ' fw-bold'"
                    },
                )
                description.text = field_node.attrib.pop(
                    "string", field_info and field_info.get("string")
                )
                container = etree.Element(
                    "div",
                    {
                        "class": "row mb-2 o_worksheet_row",
                        "style": "page-break-inside: avoid",
                    },
                )
                container.append(description)
                container.append(field_node)
                if field_node.get("invisible"):
                    condition = re.sub(
                        r'(?<![\'"])x_\w+',
                        lambda match: "worksheet." + match.group(0),
                        field_node.get("invisible"),
                    )
                    container.attrib["t-if"] = f" 0 if {condition} else 1"
                new_container_col.append(container)
        return new_container_col

    def _get_qweb_arch(self, ir_model, qweb_template_name, form_view_id=False):
        view_get_result = self.env[ir_model.model].get_view(form_view_id, "form")
        form_view_arch = view_get_result["arch"]
        node = etree.fromstring(form_view_arch)
        form_view_fields = {
            el.get("name") for el in node.xpath(".//field[not(ancestor::field)]")
        }
        form_view_fields = {
            fname: field_info
            for fname, field_info in self.env[ir_model.model].fields_get().items()
            if fname in form_view_fields
        }

        qweb_arch = etree.Element("div")
        for row_node in node.xpath(
            "//group[not(ancestor::group)]|//field[not(ancestor::group)]"
        ):
            container_row = etree.Element("div")
            container_col = etree.Element("div")
            if (
                "name" in row_node.attrib
                and row_node.attrib["name"] not in self._get_fields_qweb_arch_omitted()
                and row_node.attrib["name"] in form_view_fields
            ):
                field_node = row_node
                new_container_col = self._add_field_node_to_container(
                    field_node, form_view_fields, container_col
                )
                container_row.append(new_container_col)
                qweb_arch.append(container_row)
            else:
                cols = row_node.xpath("./group")
                if len(cols) > 0:
                    container_row = etree.Element(
                        "div", {"class": "row", "style": "page-break-inside: avoid"}
                    )
                    for col_node in cols:
                        container_col = etree.Element(
                            "div",
                            {"class": "col-6", "style": "page-break-inside: avoid"},
                        )
                        container_row.append(container_col)
                        for field_node in col_node.xpath("./field"):
                            new_container_col = self._add_field_node_to_container(
                                field_node, form_view_fields, container_col
                            )
                            container_row.append(new_container_col)
                    qweb_arch.append(container_row)
                else:
                    for field_node in row_node.xpath("./field"):
                        new_container_col = self._add_field_node_to_container(
                            field_node, form_view_fields, container_col
                        )
                        container_row.append(new_container_col)
                        qweb_arch.append(container_row)
        t_root = etree.Element("t", {"t-name": qweb_template_name})
        t_root.append(qweb_arch)
        return etree.tostring(t_root)

    def _create_qweb_report_template(self, form_view_id=False) -> None:
        for worksheet_template in self:
            report_name = worksheet_template.model_id.model.replace(".", "_")
            new_arch = self._get_qweb_arch(
                worksheet_template.model_id, report_name, form_view_id
            )
            if worksheet_template.report_view_id:
                worksheet_template.report_view_id.write({"arch": new_arch})
            else:
                report_view = self.env["ir.ui.view"].create(
                    {
                        "type": "qweb",
                        "model": False,
                        "inherit_id": False,
                        "mode": "primary",
                        "arch": new_arch,
                        "name": report_name,
                    }
                )
                self.env["ir.model.data"].create(
                    {
                        "name": "report_custom_%s" % (report_name,),
                        "module": self._get_worksheet_hooks().module,
                        "res_id": report_view.id,
                        "model": "ir.ui.view",
                        "noupdate": True,
                    }
                )
                worksheet_template.write({"report_view_id": report_view.id})
