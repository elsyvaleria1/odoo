import logging
from ast import literal_eval
from copy import deepcopy
from itertools import chain

from lxml import etree

from odoo import Command, http
from odoo.db import schema as sql
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.http import request
from odoo.libs.json import dumps as json_dumps
from odoo.tools import clean_context

_logger = logging.getLogger(__name__)

OPERATIONS_WHITELIST = [
    "add",
    "add_header_button",
    "attributes",
    "avatar_image",
    "buttonbox",
    "chatter",
    "kanban_colorpicker",
    "kanban_menu",
    "kanban_wrap_main",
    "map_popup_fields",
    "pivot_measures_fields",
    "graph_pivot_groupbys_fields",
    "move",
    "remove",
    "statusbar",
]


class WebStudioController(http.Controller):
    @http.route("/web_studio/get_studio_action", type="jsonrpc", auth="user")
    def get_studio_action(self, action_name, model, view_id=None, view_type=None):
        model = request.env["ir.model"]._get(model)

        action = None
        if action_getter := self._get_studio_action_getters().get(action_name):
            action = action_getter(model, view_id=view_id, view_type=view_type)
            if action:
                action["context"] = action.get("context", {})
                action["context"]["studio"] = 1

        return action

    def _get_studio_action_getters(self):
        return {
            "acl": self._get_studio_action_acl,
            "automation_webhooks": self._get_studio_action_automation_webhooks,
            "automations": self._get_studio_action_automations,
            "filters": self._get_studio_action_filters,
            "reports": self._get_studio_action_reports,
            "actions_server": self._get_studio_action_actions_server,
        }

    def _get_studio_action_acl(self, model, **kwargs):
        return {
            "name": request.env._("Access Control Lists"),
            "type": "ir.actions.act_window",
            "res_model": "ir.access",
            "views": [[False, "list"], [False, "form"]],
            "target": "current",
            "domain": [],
            "context": {
                "default_model_id": model.id,
                "default_kind": "permission",
                "search_default_model_id": model.id,
            },
            "help": request.env._("""<p class="o_view_nocontent_smiling_face">
                Add a new access control list
            </p>
            """),
        }

    def _get_studio_action_automation_webhooks(self, model, **kwargs):
        action = request.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "web_studio.webhook_automation_act"
        )
        action["context"] = {
            "default_model_id": model.id,
            "search_default_model_id": model.id,
            "active_test": False,
            "default_trigger": "on_webhook",
        }
        return action

    def _get_studio_action_automations(self, model, **kwargs):
        action = request.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "automation.automation_act"
        )
        action["context"] = {
            "default_model_id": model.id,
            "search_default_model_id": model.id,
            "active_test": False,
        }
        return action

    def _get_studio_action_filters(self, model, **kwargs):
        return {
            "name": request.env._("Filter Rules"),
            "type": "ir.actions.act_window",
            "res_model": "ir.filters",
            "views": [[False, "list"], [False, "form"]],
            "target": "current",
            "domain": [],
            "context": {
                "default_model_id": model.model,
                "search_default_model_id": model.model,
            },
            "help": request.env._(""" <p class="o_view_nocontent_smiling_face">
                Add a new filter
            </p>
            """),
        }

    def _get_studio_action_reports(self, model, **kwargs):
        report_name_blacklist = [
            "account_followup.report_followup_print_all",
            "stock.report_lot_label",
            "stock.report_picking_type_label",
            "product.report_producttemplatelabel2x7",
            "product.report_producttemplatelabel4x7",
            "product.report_producttemplatelabel4x12",
            "product.report_producttemplatelabel4x12noprice",
            "product.report_producttemplatelabel_dymo",
            "stock.report_reception_report_label",
            "mrp.label_production_view_pdf",
            "delivery_iot.report_shipping_labels",
            "delivery_iot.report_shipping_docs",
            "l10n_co_reports.report_libro_diario",
            "account.report_original_vendor_bill",
        ]
        report_domain = Domain.AND(
            [
                [("model_id.transient", "=", False)],
                [("model_id.abstract", "=", False)],
                [("report_type", "not in", ["qweb-text"])],
                [("report_name", "not in", report_name_blacklist)],
                [("model", "=", model.model)],
            ]
        )
        return {
            "name": request.env._(
                "Reports for %(model_name)s (%(model)s)",
                model_name=model.name,
                model=model.model,
            ),
            "type": "ir.actions.act_window",
            "res_model": "ir.actions.report",
            "views": [[False, "kanban"], [False, "form"]],
            "target": "current",
            "domain": report_domain,
            "context": {
                "default_model": model.model,
            },
            "help": request.env._(""" <p class="o_view_nocontent_empty_report">
                Add a new report
            </p>
            """),
        }

    def _get_studio_action_actions_server(self, model, **kwargs):
        return {
            "name": request.env._("Actions Server"),
            "type": "ir.actions.act_window",
            "res_model": "ir.actions.server",
            "views": [[False, "list"], [False, "form"]],
            "target": "current",
            "context": {
                "web_studio.auto_add_to_context": True,
                "default_model_id": model.id,
                "search_default_model_id": model.id,
                "search_default_action_type": True,
            },
            "help": request.env._("""<p>
                Create a new Server Action to enhance the power of the model.
            </p>
            """),
        }

    @http.route("/web_studio/create_new_app", type="jsonrpc", auth="user")
    def create_new_app(
        self,
        app_name=False,
        menu_name=False,
        model_choice=False,
        model_id=False,
        model_options=False,
        icon=None,
        context=None,
    ):
        if context:
            request.update_context(**context)
        request.update_context(studio=1)
        _logger.info('creating new app "%s" with main menu "%s"', app_name, menu_name)
        if model_choice == "existing" and model_id:
            model = request.env["ir.model"].browse(model_id)
            extra_models = request.env["ir.model"]
            _logger.info(
                "using existing model %s as main model, all main views duplicated for use in the new app",
                model.model,
            )
        elif model_choice == "new" and menu_name:
            (model, extra_models) = request.env["ir.model"].studio_model_create(
                menu_name, options=model_options
            )
            _logger.info(
                "created new model %s as main model with the following options: %s",
                model.model,
                ",".join(model_options),
            )
        else:
            _logger.error(
                "inconsistent parameters: model_choice is %s, model_id is %s and menu_name(model) is %s",
                model_choice,
                model_id,
                menu_name,
            )
            raise UserError(
                request.env._(
                    "If you don't want to create a new model, an existing model should be selected."
                )
            )

        action = model._create_default_action(menu_name)
        action_ref = "ir.actions.act_window," + str(action.id)

        menu_values = {
            "name": app_name,
        }
        child_menu_vals = [Command.create({"name": menu_name, "action": action_ref})]

        if extra_models:
            configuration_menu_vals = {
                "name": request.env._("Configuration"),
                "child_id": [],
                "is_studio_configuration": True,
                "sequence": 100,
            }
            for extra_model in extra_models:
                extra_action = extra_model._create_default_action(extra_model.name)
                configuration_menu_vals["child_id"].append(
                    (
                        0,
                        0,
                        {
                            "name": extra_model.name,
                            "action": "ir.actions.act_window," + str(extra_action.id),
                        },
                    )
                )
            child_menu_vals.append((0, 0, configuration_menu_vals))

        menu_values.update(self._get_icon_fields(icon))
        menu_values["child_id"] = child_menu_vals

        new_menu = (
            request.env["ir.ui.menu"].with_context(studio=True).create(menu_values)
        )

        return {
            "menu_id": new_menu.id,
            "action_id": action.id,
        }

    @http.route("/web_studio/create_new_menu", type="jsonrpc", auth="user")
    def create_new_menu(
        self,
        menu_name=False,
        model_choice=False,
        model_id=False,
        model_options=False,
        parent_menu_id=None,
        context=None,
    ):
        if context:
            request.update_context(**context)
        request.update_context(studio=1)
        sequence = 10
        if parent_menu_id:
            menu = request.env["ir.ui.menu"].search_read(
                [("parent_id", "=", parent_menu_id)],
                fields=["sequence"],
                order="sequence desc",
                limit=1,
            )
            if menu:
                sequence = menu[0]["sequence"] + 1

        _logger.info('creating new menu "%s"', menu_name)
        if model_choice == "existing" and model_id:
            model = request.env["ir.model"].browse(model_id)
            extra_models = request.env["ir.model"]
            _logger.info(
                "using existing model %s, all main views duplicated for use in the new app",
                model.model,
            )
        elif model_choice == "new" and menu_name:
            (model, extra_models) = request.env["ir.model"].studio_model_create(
                menu_name, options=model_options
            )
            _logger.info(
                "created new model %s with the following options: %s",
                model.model,
                ",".join(model_options),
            )
        elif model_choice == "parent":
            (model, extra_models) = (None, None)
        else:
            _logger.error(
                "inconsistent parameters: model_choice is %s, model_id is %s and menu_name(model) is %s",
                model_choice,
                model_id,
                menu_name,
            )
            raise UserError(
                request.env._(
                    "If you don't want to create a new model, an existing model should be selected."
                )
            )

        if model:
            action = model._create_default_action(menu_name)
            action_ref = "ir.actions.act_window," + str(action.id)
        else:
            action = request.env.ref("base.action_view_website")
            action_ref = "ir.actions.act_url," + str(action.id)

        new_menu = (
            request.env["ir.ui.menu"]
            .with_context(studio=True)
            .create(
                {
                    "name": menu_name,
                    "action": action_ref,
                    "parent_id": parent_menu_id,
                    "sequence": sequence,
                }
            )
        )

        if extra_models:
            config_menu = new_menu._get_or_create_studio_configuration_menu()
            child_menu_vals = []
            for extra_model in extra_models:
                extra_action = extra_model._create_default_action(extra_model.name)
                child_menu_vals.append(
                    (
                        0,
                        0,
                        {
                            "name": extra_model.name,
                            "action": "ir.actions.act_window," + str(extra_action.id),
                        },
                    )
                )
            config_menu.write({"child_id": child_menu_vals})
        return {
            "menu_id": new_menu.id,
            "action_id": action.id,
        }

    @http.route("/web_studio/edit_menu_icon", type="jsonrpc", auth="user")
    def edit_menu_icon(self, menu_id, icon, context=None):
        if context:
            request.update_context(**context)
        values = self._get_icon_fields(icon)
        request.env["ir.ui.menu"].browse(menu_id).write(values)

    def _get_icon_fields(self, icon):
        if isinstance(icon, int):
            icon_id = request.env["ir.attachment"].browse(icon)
            if not icon_id:
                raise UserError(
                    request.env._("The icon is not linked to an attachment")
                )
            return {"web_icon_data": icon_id.datas}
        elif isinstance(icon, list) and len(icon) == 3:
            return {"web_icon": ",".join(icon)}
        else:
            raise UserError(request.env._("The icon has not a correct format"))

    @http.route("/web_studio/set_background_image", type="jsonrpc", auth="user")
    def set_background_image(self, attachment_id, context=None):
        if context:
            request.update_context(**context)
        attachment = request.env["ir.attachment"].browse(attachment_id)
        if attachment:
            request.env.company.background_image = attachment.datas

    @http.route("/web_studio/reset_background_image", type="jsonrpc", auth="user")
    def reset_background_image(self, context=None):
        if context:
            request.update_context(**context)
        if (
            request.env.company
            in request.env.user.with_user(request.env.uid).company_ids
        ):
            request.env.company.background_image = None

    def create_new_field(self, values):
        model_name = values.pop("model_name")
        Model = request.env[model_name]
        table_kind = sql.get_table_kind(request.env.cr, Model._table)
        if table_kind != sql.TableKind.Regular:
            raise UserError(
                request.env._(
                    "The model %s doesn't support adding fields.", Model._name
                )
            )

        values["model_id"] = request.env["ir.model"]._get_id(model_name)

        if type_ := values.pop("type", None):
            values["ttype"] = type_

        if (string := values.get("string")) and values.get("related"):
            if request.env["ir.model.fields"].search_count(
                [("model", "=", model_name), ("field_description", "=", string)],
                limit=1,
            ):
                values["field_description"] = request.env._("%s (Copy)", string)
            else:
                values["field_description"] = string

        if rel_id := values.pop("relation_id", None):
            values["relation"] = request.env["ir.model"].browse(rel_id).model
        if (
            related := values.get("related")
            if values.get("ttype") == "one2many"
            else ""
        ):
            field_name = related.rsplit(".", 1)[-1]
            field = request.env["ir.model.fields"].search(
                [
                    ("name", "=", field_name),
                    ("model", "=", values.pop("relational_model")),
                ]
            )
            field.check_singleton()
            values.update(
                relation=field.relation,
                relation_field=field.relation_field,
            )
            if values.get("store", True) is False:
                values["relation_field"] = False
        if rel := values.pop("relation_field_id", None):
            field = request.env["ir.model.fields"].browse(rel)
            values.update(
                relation=field.model_id.model,
                relation_field=field.name,
            )
        if sel := values.get("selection"):
            values["selection"] = str(sel)

        if values.get("ttype") == "many2many":
            values["relation_table"] = request.env[
                "ir.model.fields"
            ]._get_next_relation(model_name, values.get("relation"))
        default_value = values.pop("default_value", False)

        values = {
            k: v
            for k, v in values.items()
            if k in request.env["ir.model.fields"]._fields
        }
        new_field = (
            request.env["ir.model.fields"].with_context(studio=True).create(values)
        )

        if default_value:
            if new_field.ttype == "selection":
                if default_value is True:
                    default_value = new_field.selection_ids[:1].value
            self.set_default_value(new_field.model, new_field.name, default_value)

        return new_field

    @http.route("/web_studio/add_view_type", type="jsonrpc", auth="user")
    def add_view_type(
        self, action_type, action_id, res_model, view_type, args, context=None
    ):
        if context:
            request.update_context(**context)

        if view_type == "activity":
            model = request.env["ir.model"]._get(res_model)
            if model.state == "manual" and not model.is_mail_activity:
                model.write({"is_mail_activity": True})

        try:
            request.env[res_model].with_context(no_address_format=True).get_view(
                view_type=view_type
            )
        except UserError:
            return False
        self.edit_action(action_type, action_id, args)
        return True

    @http.route("/web_studio/edit_action", type="jsonrpc", auth="user")
    def edit_action(self, action_type, action_id, args):

        action_id = request.env[action_type].browse(action_id)
        if action_id:
            if "view_mode" in args:
                if action_id.view_id or action_id.view_ids:
                    view_modes = args["view_mode"].split(",")

                    missing_view_modes = [
                        x
                        for x in view_modes
                        if x not in [y.view_mode for y in action_id.view_ids]
                    ]
                    for view_mode in missing_view_modes:
                        vals = {
                            "act_window_id": action_id.id,
                            "view_mode": view_mode,
                        }
                        if action_id.view_id and action_id.view_id.type == view_mode:
                            vals["view_id"] = action_id.view_id.id

                        request.env["ir.actions.act_window.view"].with_context(
                            studio=True
                        ).create(vals)

                    for view_id in action_id.view_ids:
                        if view_id.view_mode in view_modes:
                            view_id.sequence = view_modes.index(view_id.view_mode)
                        else:
                            view_id.unlink()

            action_id.write(args)

        return True

    def _get_studio_view(self, view):
        view = view._get_closest_primary_view()
        domain = [
            ("inherit_id", "=", view.id),
            ("name", "=", self._generate_studio_view_name(view)),
        ]
        return view.search(domain, order="priority desc, name desc, id desc", limit=1)

    def _set_studio_view(self, view, arch):
        studio_view = self._get_studio_view(view)
        if studio_view and len(arch):
            studio_view.arch_db = arch
            return studio_view
        elif studio_view:
            studio_view.unlink()
        elif len(arch):
            return self._create_studio_view(view, arch)
        return None

    def _generate_studio_view_name(self, view):
        return "Odoo Studio: %s customization" % (view.name)

    @http.route("/web_studio/get_studio_view_arch", type="jsonrpc", auth="user")
    def get_studio_view_arch(self, model, view_type, view_id=False, context=None):
        if context:
            request.update_context(**context)

        if not view_id:
            view_id = request.env["ir.ui.view"].default_view(
                request.env[model]._name, view_type
            )
        ir_model = request.env["ir.model"]._get(model)
        view = ir_model._acquire_default_view(view_type, view_id)
        studio_view = self._get_studio_view(view)

        return {
            "studio_view_id": (studio_view and studio_view.id) or False,
            "studio_view_arch": (studio_view and studio_view.arch_db) or "<data/>",
            "main_view_id": view.id,
        }

    def _return_view(self, view, studio_view, context=None):
        if context is None:
            context = {}

        ViewModel = request.env[view.model]
        fields_view = ViewModel.with_context(
            dict(context, studio=True, no_address_format=True)
        ).get_view(view.id, view.type)
        view_type = view.type
        models = fields_view["models"]

        return {
            "views": {view_type: fields_view},
            "studio_view_id": studio_view.id,
            "models": {
                model: {"fields": request.env[model].fields_get()} for model in models
            },
        }

    @http.route("/web_studio/restore_default_view", type="jsonrpc", auth="user")
    def restore_default_view(self, view_id):
        view = request.env["ir.ui.view"].browse(view_id)
        self._set_studio_view(view, "")

        studio_view = self._get_studio_view(view)

        return self._return_view(view, studio_view)

    @http.route("/web_studio/edit_view", type="jsonrpc", auth="user")
    def edit_view(
        self, view_id, studio_view_arch, operations=None, model=None, context=None
    ):
        if context:
            context_cleaned = clean_context(context)
            request.update_context(**context_cleaned)
        IrModelFields = request.env["ir.model.fields"]
        view = request.env["ir.ui.view"].browse(view_id)
        operations = operations or []
        for op in operations:
            if op["type"] not in OPERATIONS_WHITELIST:
                raise ValidationError(
                    request.env._(
                        'The operation  type "%s" is not supported', op["type"]
                    )
                )
        parser = etree.XMLParser(remove_blank_text=True)
        if studio_view_arch == "":
            studio_view_arch = "<data/>"
        arch = etree.fromstring(studio_view_arch, parser=parser)
        model = model or view.model

        def create_binary_field(op):
            node = op.get("node")
            if node and node.get("tag") == "field" and node.get("field_description"):
                ttype = node["field_description"].get("type")
                is_image = node["attrs"].get("widget") == "image"
                is_signature = node["attrs"].get("widget") == "signature"
                return ttype == "binary" and not is_image and not is_signature
            return False

        def is_monetary(op) -> bool:
            node = op.get("node")
            if node and node.get("tag") and node.get("field_description"):
                ttype = node["field_description"].get("type")
                return ttype == "monetary"
            return bool(
                node and node.get("attrs") and ("currency_field" in node.get("attrs"))
            )

        _operations = []
        for op in operations:
            _operations.append(op)
            if not create_binary_field(op):
                continue
            bin_file_field_name = op["node"]["field_description"]["name"]
            filename = bin_file_field_name + "_filename"

            char_op = deepcopy(op)
            char_op["node"]["field_description"].update(
                {
                    "name": filename,
                    "type": "char",
                    "field_description": request.env._(
                        "Filename for %s", op["node"]["field_description"]["name"]
                    ),
                    "string": f"{bin_file_field_name} Filename",
                }
            )
            node = op.get("node")
            if (
                node
                and node.get("tag") == "field"
                and node.get("field_description")
                and node["field_description"].get("related")
            ):
                model_name = node["field_description"].get("model_name") or model
                related_filename = node["field_description"]["related"] + "_filename"
                related_model_path = related_filename.split(".")[:-1]
                related_filename = request.env["ir.model.fields"]._get_related_field(
                    model_name, related_filename
                )
                if not related_filename:
                    continue
                path = ".".join(chain(related_model_path, [related_filename.name]))
                char_op["node"]["field_description"].update({"related": path})
            char_op["node"]["attrs"]["invisible"] = "True"

            char_op["target"]["xpath_info"] = None
            char_op["target"]["tag"] = "field"
            char_op["target"]["attrs"] = {"name": bin_file_field_name}
            char_op["target"]["position"] = "after"
            char_op["position"] = "after"

            _operations.append(char_op)

            op["node"]["attrs"]["filename"] = filename

        operations = _operations
        _operations = []

        for op in operations:
            if not is_monetary(op):
                _operations.append(op)
                continue
            new_field = op["node"].get("field_description")
            values = op["node"].get("field_description") or op["node"]["attrs"]
            currency_op = deepcopy(op)

            current_currency_field = new_field and new_field.get("currency_field")
            if new_field and not current_currency_field:
                currency_op["node"]["field_description"].update(
                    {
                        "name": "x_studio_currency_id",
                        "type": "many2one",
                        "relation": "res.currency",
                        "field_description": "Currency",
                    }
                )
                currency_op["node"]["field_description"].pop("string", None)

                if related := new_field.get("related"):
                    model_name = new_field.get("model_name") or model
                    related_monetary = request.env[
                        "ir.model.fields"
                    ]._get_related_field(model_name, related)
                    related_model_path = related.split(".")[:-1]
                    related_currency = (
                        related_monetary
                        and related_monetary.get_currency_field(
                            request.env[related_monetary.model_name]
                        )
                    )
                    if related_currency:
                        if not related_model_path:
                            new_field["currency_field"] = related_currency
                            currency_op["node"] = {
                                "tag": "field",
                                "attrs": {"name": related_currency},
                            }
                            current_currency_field = related_currency
                        else:
                            to_model = request.env[related_monetary.model_name]
                            related_currency = to_model._fields[related_currency]
                            path = ".".join(
                                chain(related_model_path, [related_currency.name])
                            )
                            currency_op["node"]["field_description"]["related"] = path
                            currency_op["node"]["field_description"]["store"] = False
                            new_related_field_name = path.replace(".", "_")
                            currency_op["node"]["field_description"]["name"] = (
                                f"x_studio_{new_related_field_name}"
                            )
                            currency_op["node"]["field_description"][
                                "field_description"
                            ] = f"{request.env['ir.model']._get(to_model._name).name} {related_currency.get_description(self.env, ['string'])['string']}"
                            current_currency_field = currency_op["node"][
                                "field_description"
                            ]["name"]

                if not current_currency_field:
                    currency_op["node"]["field_description"]["store"] = True
                    currency_op["node"]["field_description"].pop("related", None)
                    current_currency_field = currency_op["node"]["field_description"][
                        "name"
                    ]

                new_field["currency_field"] = current_currency_field
            else:
                currency_op["node"].pop("field_description", None)
                currency_op["node"]["attrs"] = {"name": values["currency_field"]}

            if not values.get("currency_in_view"):
                _operations.append(currency_op)

            if op["node"].get("attrs", {}).get("currency_field"):
                del op["node"]["attrs"]["currency_field"]
                del op["node"]["attrs"]["currency_in_view"]
            _operations.append(op)

        operations = _operations
        for op in operations:
            if "node" in op:
                if op["node"].get("tag") == "field" and op["node"].get(
                    "field_description"
                ):
                    is_special_lines = (
                        op["node"]["field_description"].get("special") == "lines"
                    )
                    if not is_special_lines:
                        model = op["node"]["field_description"]["model_name"]
                    field = IrModelFields.search(
                        [
                            ("name", "=", op["node"]["field_description"]["name"]),
                            ("model", "=", model),
                        ],
                        limit=1,
                    )

                    if not field:
                        if is_special_lines:
                            field = (
                                request.env["ir.model"]
                                ._get(model)
                                ._setup_one2many_lines(
                                    op["node"]["field_description"]["name"]
                                )
                            )
                        else:
                            field = self.create_new_field(
                                op["node"]["field_description"]
                            )
                    op["node"]["attrs"]["name"] = field.name
                    if field.ttype == "many2one" and op["type"] == "add":
                        create_name_field = request.env.registry[
                            field.relation
                        ]._rec_name
                        if create_name_field and create_name_field != "name":
                            op["node"]["attrs"]["options"] = (
                                "{'create_name_field': '%s'}" % create_name_field
                            )

                if op["node"].get("tag") == "filter" and op["node"]["attrs"].get(
                    "create_group"
                ):
                    op["node"]["attrs"].pop("create_group")
                    create_group_op = {
                        "node": {
                            "tag": "group",
                            "attrs": {
                                "name": "studio_group_by",
                            },
                        },
                        "empty": True,
                        "target": {
                            "tag": "search",
                        },
                        "position": "inside",
                    }
                    self._operation_add(arch, create_group_op, model)
            if view.type == "kanban":
                if op.get("target") and op["target"].get("tag") == "field":
                    op["target"]["tag"] = "templates//field"
                    if op["target"].get("extra_nodes"):
                        for target in op["target"]["extra_nodes"]:
                            target["tag"] = "templates//" + target["tag"]

            getattr(self, "_operation_%s" % (op["type"]))(arch, op, model)

        new_arch = etree.tostring(arch, encoding="unicode", pretty_print=True)
        studio_view = self._get_studio_view(view)
        try:
            normalized_view = (studio_view or view).normalize(new_arch)
            studio_view = self._set_studio_view(view, normalized_view)
        except ValidationError:
            studio_view = self._set_studio_view(view, new_arch)

        return self._return_view(
            view, studio_view or request.env["ir.ui.view"], context
        )

    @http.route("/web_studio/rename_field", type="jsonrpc", auth="user")
    def rename_field(
        self,
        studio_view_id,
        studio_view_arch,
        model,
        old_name,
        new_name,
        new_label=None,
    ):
        studio_view = request.env["ir.ui.view"].browse(studio_view_id)

        studio_view.arch_db = studio_view_arch

        field_id = (
            request.env["ir.model.fields"]._get(model, old_name).with_context(lang=None)
        )
        to_write = {"name": new_name}
        if new_label is not None:
            to_write["field_description"] = new_label
        field_id.write(to_write)

        if field_id.ttype == "binary" and not field_id.related:
            filename_field_id = request.env["ir.model.fields"]._get(
                model, old_name + "_filename"
            )
            if filename_field_id:
                filename_field_id.write({"name": new_name + "_filename"})

    @http.route("/web_studio/get_actions_for_model", type="jsonrpc", auth="user")
    def get_actions_for_model(self, model):
        actions_list = {}
        actions_for_model = request.env["ir.actions.actions"].search(
            [("binding_model_id", "=", model)]
        )
        actions_types = {}
        for action in actions_for_model:
            actions_types.setdefault(action.type, []).append(action.id)
        for action_type, action_ids in actions_types.items():
            actions = request.env[action_type].browse(action_ids)
            for action in actions:
                actions_list[action.id] = {
                    "name": action.display_name,
                    "xml_id": action.xml_id or action.id,
                }

        server_actions_for_model = request.env["ir.actions.server"].search(
            [("model_id", "=", model), ("binding_model_id", "=", False)]
        )
        for action in server_actions_for_model:
            actions_list[action.id] = {
                "name": action.display_name,
                "xml_id": action.xml_id,
            }
        return actions_list

    def _create_studio_view(self, view, arch):
        view = view._get_closest_primary_view()
        priority = max(view.inherit_children_ids.mapped("priority"), default=0) * 10
        default_prio = view._fields["priority"].default(view)
        if priority <= default_prio:
            priority = 99
        return (
            request.env["ir.ui.view"]
            .with_context(studio=True)
            .create(
                {
                    "type": view.type,
                    "model": view.model,
                    "inherit_id": view.id,
                    "mode": "extension",
                    "priority": priority,
                    "arch": arch,
                    "name": self._generate_studio_view_name(view),
                }
            )
        )

    @http.route("/web_studio/edit_field", type="jsonrpc", auth="user")
    def edit_field(self, model_name, field_name, values, force_edit=False):
        field = request.env["ir.model.fields"].search(
            [("model", "=", model_name), ("name", "=", field_name)]
        )

        if field.ttype == "selection" and "selection" in values:
            selection_values = [False] + [
                x[0] for x in literal_eval(values["selection"])
            ]
            records = request.env[model_name].search(
                [(field_name, "not in", selection_values)]
            )
            if records and not force_edit:
                message = request.env._(
                    """There are %s records using selection values not listed in those you are trying to save.
Are you sure you want to remove the selection values of those records?""",
                    len(records),
                )
                return {"records_linked": len(records), "message": message}
            records.write({field_name: False})

        field.write(values)

        if field.ttype == "selection":
            current_default = request.env["ir.default"]._get(
                model_name, field_name, company_id=True
            )
            if current_default:
                selection_values = literal_eval(field.selection)
                if current_default not in [x[0] for x in selection_values]:
                    request.env["ir.default"].discard_values(
                        model_name, field_name, [current_default]
                    )
        return None

    @http.route("/web_studio/edit_view_arch", type="jsonrpc", auth="user")
    def edit_view_arch(self, view_id, view_arch, context=None):
        if context:
            context_cleaned = clean_context(context)
            request.update_context(**context_cleaned)
        view = request.env["ir.ui.view"].browse(view_id)
        if view:
            view.write({"arch": view_arch})
            studio_view = self._get_studio_view(view)
            return self._return_view(view, studio_view, context)
        return None

    @http.route("/web_studio/create_default_view", type="jsonrpc", auth="user")
    def create_default_view(self, model, view_type, attrs):
        attrs["string"] = "Default %s view for %s" % (view_type, model)
        arch = self._get_default_view(view_type, attrs)
        request.env["ir.ui.view"].with_context(studio=True).create(
            {
                "type": view_type,
                "model": model,
                "arch": arch,
                "name": attrs["string"],
            }
        )

    def _get_default_view(self, view_type, attrs):
        arch = etree.Element(view_type, attrs)
        return etree.tostring(
            arch, encoding="unicode", pretty_print=True, method="html"
        )

    def _node_to_expr(self, node):
        if node.get("xpath_info"):
            expr_list = node.get("xpath_info")
            if node.get("subview_xpath"):
                expr_list = expr_list[1:]
            expr = "".join(
                ["/%s[%s]" % (parent["tag"], parent["indice"]) for parent in expr_list]
            )
        else:
            expr = "//" + node["tag"]
            for k, v in node.get("attrs", {}).items():
                if k == "class":
                    clx = v.strip().split(" ")
                    if clx:
                        str_classes = ",".join(f"'{cls}'" for cls in clx)
                        expr += f"[hasclass({str_classes})]"
                else:
                    expr += "[@%s='%s']" % (k, v)

            if not node.get("subview_xpath"):
                expr += "[not(ancestor::field)]"

        if node.get("subview_xpath"):
            xpath = node.get("subview_xpath")
            if node.get("isSubviewAttr"):
                expr = xpath
            elif not xpath.endswith(expr):
                expr = xpath + expr
        return expr

    def _get_xpath_node(self, arch, operation):
        expr = self._node_to_expr(operation["target"])
        position = operation["position"]

        return etree.SubElement(arch, "xpath", {"expr": expr, "position": position})

    def _operation_remove(self, arch, operation, model=None):
        expr = self._node_to_expr(operation["target"])

        etree.SubElement(arch, "xpath", {"expr": expr, "position": "replace"})
        if operation["target"].get("extra_nodes"):
            for target in operation["target"]["extra_nodes"]:
                expr = self._node_to_expr(target)
                etree.SubElement(arch, "xpath", {"expr": expr, "position": "replace"})

    def _operation_replace(self, arch, operation, model):
        target_expr = self._node_to_expr(operation["target"])

        replace_xpath = etree.SubElement(
            arch, "xpath", {"expr": target_expr, "position": "replace"}
        )

        replace_with = operation["node"]
        etree.SubElement(replace_xpath, replace_with["tag"], replace_with["attrs"])

    def _operation_add(self, arch, operation, model):
        node = operation["node"]
        xpath_node = self._get_xpath_node(arch, operation)

        def add_columns(xml_node):
            name = "studio_group_" + xml_node.get("name").split("_")[2]

            if xml_node.tag != "group":
                xml_node_group = etree.SubElement(xml_node, "group", {"name": name})
            else:
                xml_node_group = xml_node

            etree.SubElement(xml_node_group, "group", {"name": name + "_left"})
            etree.SubElement(xml_node_group, "group", {"name": name + "_right"})

        xml_node = etree.Element(node["tag"], node.get("attrs"))
        if node["tag"] == "notebook":
            name = "studio_page_" + node["attrs"]["name"].split("_")[2]
            xml_node_page = etree.Element("page", {"string": "New Page", "name": name})
            add_columns(xml_node_page)
            xml_node.insert(0, xml_node_page)
        elif node["tag"] == "page":
            add_columns(xml_node)
        elif node["tag"] == "group":
            if "empty" not in operation:
                add_columns(xml_node)
        elif node["tag"] == "button":
            button_field = request.env["ir.model.fields"].browse(node["field"])
            button_count_field, button_action = self._get_or_create_fields_for_button(
                model, button_field, node["string"]
            )

            xml_node_field = etree.Element(
                "field",
                {
                    "widget": "statinfo",
                    "name": button_count_field.name,
                    "string": node["string"] or button_count_field.field_description,
                },
            )
            xml_node.insert(0, xml_node_field)

            xml_node.attrib["type"] = "action"
            xml_node.attrib["name"] = str(button_action.xml_id)
        else:
            xml_node.text = node.get("text")
        xpath_node.insert(0, xml_node)

    def _get_or_create_fields_for_button(self, model, field, button_name):

        if field.ttype not in ("many2one", "many2many") or field.relation != model:
            raise UserError(
                request.env._(
                    "The related field of a button has to be a many2one to %s.", model
                )
            )

        model = request.env["ir.model"]._get(model)

        button_count_field_name = (
            "x_%s_%s_count" % (field.name, field.model.replace(".", "_"))[0:63]
        )
        button_count_field = request.env["ir.model.fields"].search(
            [("name", "=", button_count_field_name), ("model_id", "=", model.id)]
        )
        if not button_count_field:
            compute_function = """
                    for record in self: record['%(count_field)s'] = self.env['%(model)s'].search_count([('%(field)s', '=', record.id)])
                """ % {
                "model": field.model,
                "field": field.name,
                "count_field": button_count_field_name,
            }
            button_count_field = (
                request.env["ir.model.fields"]
                .with_context(studio=True)
                .create(
                    {
                        "name": button_count_field_name,
                        "field_description": "%s count" % field.field_description,
                        "model": model.model,
                        "model_id": model.id,
                        "ttype": "integer",
                        "store": False,
                        "compute": compute_function.replace(
                            "    ", ""
                        ),
                    }
                )
            )

        button_action_domain = "[('%s', '=', active_id)]" % (field.name)
        active_id = "active_id" if field.ttype == "many2one" else "[active_id]"
        button_action_context = "{'search_default_%s': active_id,'default_%s': %s}" % (
            field.name,
            field.name,
            active_id,
        )
        button_action = request.env["ir.actions.act_window"].search(
            [
                ("name", "=", button_name),
                ("res_model", "=", field.model),
                ("domain", "=", button_action_domain),
                ("context", "=", button_action_context),
            ]
        )
        if not button_action:
            button_action = (
                request.env["ir.actions.act_window"]
                .with_context(studio=True)
                .create(
                    {
                        "name": button_name,
                        "res_model": field.model,
                        "view_mode": "list,form",
                        "domain": button_action_domain,
                        "context": button_action_context,
                    }
                )
            )

        return button_count_field, button_action

    def _operation_move(self, arch, operation, model=None):
        xpath_node = self._get_xpath_node(arch, operation)
        xml_node = etree.Element(
            "xpath",
            {
                "expr": self._node_to_expr(operation["node"]),
                "position": "move",
            },
        )
        xpath_node.append(xml_node)

    def _operation_attributes(self, arch, operation, model=None):
        ir_model_data = request.env["ir.model.data"]
        new_attrs = operation["new_attrs"]

        if "groups" in new_attrs:
            eval_attr = []
            group_ids = {}
            for many2many_value in new_attrs["groups"]:
                if isinstance(many2many_value, str) and many2many_value.startswith("!"):
                    allow = False
                    _id = int(many2many_value[1:])
                else:
                    allow = True
                    _id = int(many2many_value)
                group_ids[_id] = allow

            if group_ids:
                xml_ids = {
                    imd["res_id"]: imd["complete_name"]
                    for imd in ir_model_data.search_read(
                        [
                            ("model", "=", "res.groups"),
                            ("res_id", "in", list(group_ids.keys())),
                        ],
                        ["res_id", "complete_name"],
                    )
                }

                for g_id, allow in group_ids.items():
                    if g_id not in xml_ids:
                        raise UserError(
                            request.env._(
                                "Only groups with an external ID can be used here. Please choose another "
                                "group or assign manually an external ID to this group."
                            )
                        )
                    group_attr = xml_ids[g_id]
                    if not allow:
                        group_attr = "!" + group_attr

                    eval_attr.append(group_attr)
            eval_attr = ",".join(eval_attr)
            new_attrs["groups"] = eval_attr

        if new_attrs.get("type") and operation["target"]["tag"] == "button":
            new_attrs["name"] = ""
        xpath_node = self._get_xpath_node(arch, operation)

        for key, new_attr in new_attrs.items():
            xml_node = etree.Element("attribute", {"name": key})
            if new_attr is not None:
                xml_node.text = (
                    json_dumps(new_attr)
                    if isinstance(new_attr, bool)
                    else str(new_attr)
                )
            xpath_node.insert(0, xml_node)

            if key == "string" and operation.get("node", {}).get("tag") == "field":
                field_name = operation.get("node", {}).get("attrs", {}).get("name")
                field_id = request.env["ir.model.fields"].search(
                    [("model", "=", model), ("name", "=", field_name)]
                )
                if (
                    field_id
                    and request.env["ir.model"]._is_manual_name(field_name)
                    and field_id.field_description != new_attr
                ):
                    field_id.write({"field_description": new_attr})

    def _operation_buttonbox(self, arch, operation, model=None):
        studio_view_arch = arch
        arch = (
            request.env[model]
            .with_context(studio=True, no_address_format=True)
            .get_view(view_type="form")["arch"]
        )
        parser = etree.XMLParser(remove_blank_text=True)
        arch = etree.fromstring(arch, parser=parser)

        sheet_node = arch.find("sheet")
        if sheet_node is not None:
            if list(sheet_node):
                xpath_node = etree.SubElement(
                    studio_view_arch,
                    "xpath",
                    {"expr": "//sheet/*[1]", "position": "before"},
                )
            else:
                xpath_node = etree.SubElement(
                    studio_view_arch, "xpath", {"expr": "//sheet", "position": "inside"}
                )
            buttonbox_node = etree.Element(
                "div", {"name": "button_box", "class": "oe_button_box"}
            )
            xpath_node.append(buttonbox_node)

    def _operation_add_header_button(self, arch, operation, model):
        actions_for_model = self.get_actions_for_model(model)
        type = "action" if len(actions_for_model) > 0 else "object"
        params = {"string": "New Button", "type": type}
        expression = "//header[1]"
        position = "inside"
        xpath_node = arch.find(f'xpath[@expr="{expression}"][@position="{position}"]')
        if xpath_node is None:
            xpath_node = etree.SubElement(
                arch,
                "xpath",
                {
                    "expr": expression,
                    "position": position,
                },
            )

        statusbarbutton = etree.Element("button", params)
        xpath_node.append(statusbarbutton)

    def _operation_chatter(self, arch, operation, model=None):
        def _get_remove_field_op(arch, field_name):
            return {
                "type": "remove",
                "target": {
                    "tag": "field",
                    "attrs": {
                        "name": field_name,
                    },
                },
            }

        Model = request.env[operation["model"]]
        if not (
            Model._custom
            or isinstance(Model, request.env.registry["mixin.mail.thread"])
        ):
            return

        model = request.env["ir.model"]._get(operation["model"])
        if model.state == "manual" and not model.is_mail_thread:
            model.write({"is_mail_thread": True})
        if model.state == "manual" and not model.is_mail_activity:
            model.write({"is_mail_activity": True})

        if operation["remove_message_ids"]:
            self._operation_remove(arch, _get_remove_field_op(arch, "message_ids"))
        if operation["remove_follower_ids"]:
            self._operation_remove(
                arch, _get_remove_field_op(arch, "message_follower_ids")
            )
        if operation["remove_activity_ids"]:
            self._operation_remove(arch, _get_remove_field_op(arch, "activity_ids"))

        xpath_node = etree.SubElement(
            arch,
            "xpath",
            {
                "expr": "//sheet",
                "position": "after",
            },
        )
        chatter_node = etree.Element("chatter")
        xpath_node.append(chatter_node)

    def _operation_kanban_wrap_main(self, arch, operation, model):
        wrap_type = operation.get("wrap_type")
        main_node = etree.fromstring("<t t-name='card'><main>$0</main></t>")
        etree.SubElement(
            arch,
            "xpath",
            {"expr": '//t[@t-name="card"]', "position": "replace", "mode": "outer"},
        ).append(main_node)
        if wrap_type == "aside":
            xpath_node = etree.SubElement(
                arch, "xpath", {"expr": '//t[@t-name="card"]', "position": "attributes"}
            )
            attribute_node = etree.Element("attribute", name="class")
            attribute_node.text = "row g-0"
            xpath_node.append(attribute_node)
            xpath_node_main = etree.SubElement(
                arch, "xpath", {"expr": "//main", "position": "attributes"}
            )
            attribute_node_main = etree.Element("attribute", name="class")
            attribute_node_main.text = "col-10"
            xpath_node_main.append(attribute_node_main)
        xpath_node = etree.SubElement(
            arch,
            "xpath",
            {"expr": '//main/t[@t-name="card"]', "position": "attributes"},
        )
        xpath_node.append(etree.Element("attribute", name="t-name"))

    def _operation_kanban_colorpicker(self, arch, operation, model):
        view_id = operation.get("view_id")
        view = request.env["ir.ui.view"].browse(view_id)
        base_view = etree.fromstring(view.get_combined_arch())

        color_field = base_view.get("highlight_color")
        if color_field is None:
            model_id = request.env["ir.model"]._get_id(model)
            if not model_id:
                return

            color_field = "x_color"
            if not request.env["ir.model.fields"].search_count(
                [
                    ("model_id", "=", model_id),
                    ("name", "=", color_field),
                    ("ttype", "=", "integer"),
                ],
                limit=1,
            ):
                request.env["ir.model.fields"].create(
                    {
                        "model": model,
                        "model_id": model_id,
                        "name": color_field,
                        "field_description": "Card color",
                        "ttype": "integer",
                    }
                )
            etree.SubElement(
                arch,
                "xpath",
                {
                    "expr": "//kanban",
                    "position": "attributes",
                },
            ).append(
                etree.fromstring(
                    f"<attribute name='highlight_color'>{color_field}</attribute>"
                )
            )

        etree.SubElement(
            arch,
            "xpath",
            {
                "expr": './/t[@t-name="menu"]',
                "position": "inside",
            },
        ).append(
            etree.fromstring(
                f"<field name='{color_field}' widget='kanban_color_picker'></field>"
            )
        )

    def _operation_kanban_menu(self, arch, operation, model):
        menu_node = etree.fromstring("""
            <t t-name="menu">
                <t t-if="widget.editable"><a type="open" class="dropdown-item">Edit</a></t>
                <t t-if="widget.deletable"><a type="delete" class="dropdown-item">Delete</a></t>
            </t>
        """)
        etree.SubElement(
            arch,
            "xpath",
            {
                "expr": '//t[@t-name="card"]',
                "position": "before",
            },
        ).append(menu_node)

    def _operation_avatar_image(self, arch, operation, model):
        studio_view_arch = arch
        arch = (
            request.env[model]
            .with_context(studio=True, no_address_format=True)
            .get_view(view_type="form")["arch"]
        )
        parser = etree.XMLParser(remove_blank_text=True)
        arch = etree.fromstring(arch, parser=parser)

        model_id = request.env["ir.model"]._get_id(model)
        IrModelFields = request.env["ir.model.fields"]

        if not model_id:
            raise UserError(request.env._("The model %s does not exist.", model))
        if operation.get("field"):
            field_id = IrModelFields.search(
                [("model", "=", model), ("name", "=", operation["field"])]
            )
            if not field_id:
                raise UserError(
                    request.env._("The field %s does not exist.", operation["field"])
                )
        else:
            field_id = IrModelFields.search(
                [
                    ("model_id", "=", model_id),
                    ("name", "=", "x_avatar_image"),
                    ("ttype", "=", "binary"),
                ]
            )
            if not field_id:
                field_id = IrModelFields.with_context(studio=True).create(
                    {
                        "model": model,
                        "model_id": model_id,
                        "name": "x_avatar_image",
                        "field_description": "Avatar",
                        "ttype": "binary",
                    }
                )
        attrs = {
            "expr": '//div[hasclass("oe_title")]',
            "position": "before",
        }
        hasFlexH1 = (
            arch.xpath("//div[hasclass('oe_title')]//h1[hasclass('d-flex')]") and True
        )
        if hasFlexH1:
            attrs.update(
                {
                    "expr": "//div[hasclass('oe_title')]//h1[hasclass('d-flex')]",
                    "position": "inside",
                }
            )
        avatar_class = "oe_avatar ml-3 h4" if hasFlexH1 else "oe_avatar ml-3 mr-3"
        etree.SubElement(studio_view_arch, "xpath", attrs).append(
            etree.fromstring(
                """
                <field name="%s" widget="image" class="%s"/>
            """
                % (field_id.name, avatar_class)
            )
        )

    def _operation_statusbar(self, arch, operation, model=None):
        xpath_node = etree.SubElement(
            arch,
            "xpath",
            {
                "expr": "//form[1]/*[1] | //list[1]/*[1] | //kanban[1]/*[1]",
                "position": "before",
            },
        )
        xpath_node.append(etree.Element("header"))

    def _operation_map_popup_fields(self, arch, operation, model):
        fields = request.env["ir.model.fields"].browse(operation["target"]["field_ids"])
        for field in fields:
            if operation["target"]["operation_type"] == "add":
                op = {
                    "node": {
                        "tag": "field",
                        "attrs": {
                            "name": field.name,
                            "string": field.field_description,
                        },
                    },
                    "target": {
                        "tag": "map",
                    },
                    "position": "inside",
                }
                self._operation_add(arch, op, model)
            else:
                op = {
                    "type": "remove",
                    "target": {
                        "tag": "field",
                        "attrs": {
                            "name": field.name,
                        },
                    },
                }
                self._operation_remove(arch, op)

    def _operation_pivot_measures_fields(self, arch, operation, model):
        fields = request.env["ir.model.fields"].browse(operation["target"]["field_ids"])
        for field in fields:
            if operation["target"]["operation_type"] == "add":
                op = {
                    "node": {
                        "tag": "field",
                        "attrs": {
                            "name": field.name,
                            "type": "measure",
                        },
                    },
                    "target": {
                        "tag": "pivot",
                    },
                    "position": "inside",
                }
                self._operation_add(arch, op, model)
            else:
                op = {
                    "type": "remove",
                    "target": {
                        "tag": "field",
                        "attrs": {
                            "name": field.name,
                        },
                    },
                }
                self._operation_remove(arch, op)

    def _operation_graph_pivot_groupbys_fields(self, arch, operation, model):
        fieldsName = request.env["ir.model.fields"].search(
            [
                ("name", "in", operation["target"]["field_names"]),
                ("model", "=", model),
            ]
        )
        for field in fieldsName:
            if operation["target"]["operation_type"] == "add":
                op = {
                    "node": {
                        "tag": "field",
                        "attrs": {
                            "name": field.name,
                            "type": operation["target"]["field_type"],
                        },
                    },
                    "target": {
                        "tag": operation["target"]["view_type"],
                    },
                    "position": "inside",
                }
                self._operation_add(arch, op, model)
            elif operation["target"]["operation_type"] == "replace":
                op = {
                    "node": {
                        "tag": "field",
                        "attrs": {
                            "name": field.name,
                            "type": operation["target"]["field_type"],
                        },
                    },
                    "target": {
                        "tag": "field",
                        "attrs": {
                            "name": operation["target"]["old_field_names"],
                        },
                    },
                }
                self._operation_replace(arch, op, model)
            else:
                op = {
                    "type": "remove",
                    "target": {
                        "tag": "field",
                        "attrs": {
                            "name": field.name,
                        },
                    },
                }
                self._operation_remove(arch, op)

    @http.route("/web_studio/get_email_alias", type="jsonrpc", auth="user")
    def get_email_alias(self, model_name):
        current_alias_domain = request.env.company.alias_domain_id
        result = {"alias_domain": current_alias_domain.name}

        model = request.env["ir.model"]._get(model_name)
        if not model:
            return result

        request.env[model_name].check_access("read")
        email_alias = request.env["mail.alias"].search(
            [
                ("alias_domain_id", "=", current_alias_domain.id),
                ("alias_force_thread_id", "=", False),
                ("alias_model_id", "=", model.id),
                ("alias_parent_model_id", "=", False),
                ("alias_parent_thread_id", "=", False),
            ],
            limit=1,
        )
        result["email_alias"] = email_alias.alias_name
        return result

    @http.route("/web_studio/set_email_alias", type="jsonrpc", auth="user")
    def set_email_alias(self, model_name, value):
        model_id = request.env["ir.model"]._get_id(model_name)
        if not model_id:
            return

        request.env[model_name].check_access("read")
        current_alias_domain = request.env.company.alias_domain_id
        alias_name = request.env["mail.alias"]._normalize_alias_name(value)
        existing_alias = request.env["mail.alias"].search(
            [
                ("alias_domain_id", "=", current_alias_domain.id),
                ("alias_force_thread_id", "=", False),
                ("alias_model_id", "=", model_id),
                ("alias_parent_model_id", "=", False),
                ("alias_parent_thread_id", "=", False),
            ],
            limit=1,
        )
        if existing_alias:
            existing_alias.alias_name = alias_name
        elif alias_name:
            request.env["mail.alias"].with_context(studio=True).create(
                {
                    "alias_domain_id": current_alias_domain.id,
                    "alias_model_id": model_id,
                    "alias_name": alias_name,
                }
            )

    @http.route("/web_studio/get_default_value", type="jsonrpc", auth="user")
    def get_default_value(self, model_name, field_name, company_id=False):
        context = {}
        if company_id:
            context["allowed_company_ids"] = [company_id]
        return {
            "default_value": request.env["ir.default"]
            .with_context(context)
            ._get(model_name, field_name, company_id=True)
        }

    @http.route("/web_studio/set_default_value", type="jsonrpc", auth="user")
    def set_default_value(self, model_name, field_name, value, company_id=False):
        context = {"studio": True}
        if company_id:
            context["allowed_company_ids"] = [company_id]
        request.env["ir.default"].with_context(context).set(
            model_name, field_name, value, company_id=True
        )

    @http.route("/web_studio/set_currency", type="jsonrpc", auth="user")
    def set_currency(self, model_name, field_name, value):
        return (
            request.env["ir.model.fields"]
            .with_context(studio=True)
            .search([["model", "=", model_name], ["name", "=", field_name]])
            .write({"currency_field": value})
        )

    @http.route("/web_studio/create_inline_view", type="jsonrpc", auth="user")
    def create_inline_view(
        self, model, view_id, field_name, subview_type, subview_xpath, context=None
    ):
        if context:
            request.update_context(**context)
        view = request.env["ir.ui.view"].browse(view_id)
        studio_view = self._get_studio_view(view)
        if not studio_view:
            studio_view = self._create_studio_view(view, "<data/>")
        parser = etree.XMLParser(remove_blank_text=True)
        arch = etree.fromstring(studio_view.arch_db, parser=parser)
        position = "inside"
        xpath_node = arch.find(
            'xpath[@expr="%s"][@position="%s"]' % (subview_xpath, position)
        )
        if xpath_node is None:
            xpath_node = etree.SubElement(
                arch, "xpath", {"expr": subview_xpath, "position": position}
            )
        view_arch, _ = (
            request.env[model]
            .with_context(no_address_format=True)
            ._get_view(view_type=subview_type)
        )
        xml_node = self._inline_view_filter_nodes(view_arch)
        xpath_node.insert(0, xml_node)
        studio_view.arch_db = etree.tostring(arch, encoding="utf-8", pretty_print=True)
        return studio_view.arch_db

    def _inline_view_filter_nodes(self, inline_view_etree):
        unwanted_xpath = [
            "//chatter",
            "*[hasclass('o_attachment_preview')]",
        ]
        for path in unwanted_xpath:
            for node in inline_view_etree.xpath(path):
                inline_view_etree.remove(node)

        return inline_view_etree
