import re
import unicodedata
import uuid
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Literal

from odoo import Command, api, models
from odoo.exceptions import ValidationError

if TYPE_CHECKING:
    from odoo.addons.base.models.ir_ui_view import IrUiView

OPTIONS_WL = [
    "use_mail",  # add mail_thread to record
    "use_active",  # allows to archive records (active field)
    "use_responsible",  # add user field
    "use_partner",  # adds partner and related phone and email fields
    "use_company",  # add company field and corresponding access rules
    "use_notes",  # html note field
    "use_date",  # date field
    "use_double_dates",  # date start and date begin
    "use_value",  # value and currency
    "use_image",  # image field
    "use_sequence",  # allows to order records (sequence field)
    "lines",  # create a default One2Many targeting a generated lines models
    "use_stages",  # add stages and stage model to record (kanban)
    "use_tags",  # add tags and tags model to record (kanban)
]


def normalize_for_xmlid(s):
    """Transforms a string to a name suitable for use in an xmlid.
    Strips leading and trailing spaces, converts unicode chars to ascii,
    lowers all chars, replaces spaces with underscores and truncates the
    resulting string to 20 characters.

    :type s: str
    :rtype: str
    """
    uni = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")

    slug_str = re.sub(r"\W", " ", uni).strip().lower()
    slug_str = re.sub(r"[-\s]+", "_", slug_str)
    return slug_str[:20]


class Base(models.AbstractModel):
    _inherit = "base"

    def create_studio_model_data(self, name) -> None:
        """We want to keep track of created records with studio
        (ex: model, field, view, action, menu, etc.).
        An ir.model.data is created whenever a record of one of these models
        is created, tagged with studio.
        """
        IrModelData = self.env["ir.model.data"]

        # Check if there is already an ir.model.data for the given resource
        data = IrModelData.search(
            [("model", "=", self._name), ("res_id", "=", self.id)]
        )
        if data:
            data.write(
                {}
            )  # force a write to set the 'studio' and 'noupdate' flags to True
        else:
            module = self.env["ir.module.module"].get_or_create_studio_module()
            IrModelData.create(
                {
                    "name": "%s_%s"
                    % (normalize_for_xmlid(name or "False"), uuid.uuid4()),
                    "model": self._name,
                    "res_id": self.id,
                    "module": module.name,
                }
            )

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        if self.env.context.get("studio") and self.env.user.has_group(
            "base.group_system"
        ):
            return super(Base, self.sudo()).fields_get(allfields, attributes=attributes)
        return super().fields_get(allfields, attributes=attributes)


class IrModel(models.Model):
    _name = "ir.model"
    _inherit = ["mixin.studio", "ir.model"]

    @api.model
    def studio_model_create(self, name, options=()) -> tuple:
        """Allow quick creation of models through Studio.

        :param name: functional name of the model (_description attribute)
        :param options: list of options that can trigger automated behaviours,
                        in the form of 'use_<behaviour>' (e.g. 'use_tags')
        :return: the main model created as well as extra models needed for the
                 requested behaviours (e.g. tag or stage models) in the form of
                 a tuple (main_model, extra_models)
        :rtype: tuple
        """
        options = set(options)
        use_mail = "use_mail" in options

        model_values = {
            "name": name,
            "model": "x_" + normalize_for_xmlid(name),
            "is_mail_thread": use_mail,
            "is_mail_activity": use_mail,
            "field_id": [
                Command.create(
                    {
                        "name": "x_name",
                        "ttype": "char",
                        "required": True,
                        "field_description": self.env._("Description"),
                        "translate": "standard",
                        "tracking": use_mail,
                    }
                )
            ],
        }

        # now let's check other options and accumulate potential extra models (tags, stages)
        # created during this process, they will need to get their own action and menu
        # (which will be done at the controller level)
        extra_models_keys = []
        extra_models_values = []

        options.discard("use_mail")
        for option in OPTIONS_WL:
            if option in options:
                method = f"_create_option_{option}"
                model_to_create = getattr(self, method)(model_values)
                if model_to_create:
                    extra_models_keys.append(option)
                    extra_models_values.append(model_to_create)

        all_models = self.create([model_values] + extra_models_values)
        main_model, *extra_models = all_models
        extra_models_dict = dict(zip(extra_models_keys, extra_models, strict=False))

        all_models._setup_access_rights()

        for option in OPTIONS_WL:
            if option in options:
                method = f"_post_create_option_{option}"
                getattr(main_model, method, lambda m: None)(
                    extra_models_dict.get(option)
                )

        self.env["ir.ui.view"].create_automatic_views(main_model.model)

        ListEditableView = self.env["ir.ui.view"].with_context(list_editable="bottom")
        for extra_model in extra_models:
            ListEditableView.create_automatic_views(extra_model.model)

        models_with_menu = self.browse(
            model.id
            for key, model in extra_models_dict.items()
            if key in ("use_stages", "use_tags")
        )
        return (main_model, models_with_menu)

    @api.model
    def name_create(self, name):
        if self.env.context.get("studio"):
            (main_model, _) = self.studio_model_create(name)
            return main_model.id, main_model.display_name
        return super().name_create(name)

    def _create_option_lines(self, model_vals):
        """Creates a new model (with sequence and description fields) and a
        one2many field pointing to that model.
        """
        # create the Line model
        line_model_values, field_values = self._values_lines(model_vals.get("model"))

        model_vals["field_id"].append(Command.create(field_values))
        return line_model_values

    def _setup_one2many_lines(self, one2many_name=None):
        # create the Line model
        model_values, field_values = self._values_lines(self.model, one2many_name)
        line_model = self.create(model_values)
        line_model._setup_access_rights()
        self.env["ir.ui.view"].create_automatic_views(line_model.model)
        field_values["model_id"] = self.id
        return self.env["ir.model.fields"].create(field_values)

    def _values_lines(self, model_name, one2many_name=None) -> tuple:
        """Build the values for a Line model (with sequence and description
        fields) and for a one2many field pointing to it.
        """
        # create the Line model
        model_table = model_name.replace(".", "_")
        if not self._is_manual_name(model_table):
            model_table = "x_" + model_table
        model_line_name = model_table[2:] + "_line"
        model_line_model = model_table + "_line_" + uuid.uuid4().hex[:5]
        relation_field_name = model_table + "_id"
        line_model_values = {
            "name": model_line_name,
            "model": model_line_model,
            "field_id": [
                Command.create(
                    {
                        "name": "x_studio_sequence",
                        "ttype": "integer",
                        "field_description": self.env._("Sequence"),
                    }
                ),
                Command.create(
                    {
                        "name": "x_name",
                        "ttype": "char",
                        "required": True,
                        "field_description": self.env._("Description"),
                        "translate": "standard",
                    }
                ),
                Command.create(
                    {
                        "name": relation_field_name,
                        "ttype": "many2one",
                        "relation": model_name,
                    }
                ),
            ],
        }
        field_values = {
            "name": one2many_name or model_table + "_line_ids_" + uuid.uuid4().hex[:5],
            "ttype": "one2many",
            "relation": model_line_model,
            "relation_field": relation_field_name,
            "field_description": self.env._("New Lines"),
        }
        return line_model_values, field_values

    def _create_option_use_active(self, model_vals) -> None:
        model_vals["field_id"].append(
            Command.create(
                {
                    "name": "x_active",  # can't use x_studio_active as not supported by ORM
                    "ttype": "boolean",
                    "field_description": self.env._("Active"),
                    "tracking": model_vals.get("is_mail_thread"),
                }
            )
        )

    def _post_create_option_use_active(self, _model) -> None:
        self.env["ir.default"].set(self.model, "x_active", True)

    def _create_option_use_sequence(self, model_vals) -> None:
        model_vals["field_id"].append(
            Command.create(
                {
                    "name": "x_studio_sequence",
                    "ttype": "integer",
                    "field_description": self.env._("Sequence"),
                    "copied": True,
                }
            )
        )
        model_vals["order"] = "x_studio_sequence asc, id asc"

    def _post_create_option_use_sequence(self, _model) -> None:
        self.env["ir.default"].set(self.model, "x_studio_sequence", 10)

    def _create_option_use_responsible(self, model_vals) -> None:
        model_vals["field_id"].append(
            Command.create(
                {
                    "name": "x_studio_user_id",
                    "ttype": "many2one",
                    "relation": "res.users",
                    "domain": "[('share', '=', False)]",
                    "field_description": self.env._("Responsible"),
                    "copied": True,
                    "tracking": model_vals.get("is_mail_thread"),
                }
            )
        )

    def _create_option_use_partner(self, model_vals) -> None:
        model_vals["field_id"].append(
            Command.create(
                {
                    "name": "x_studio_partner_id",
                    "ttype": "many2one",
                    "relation": "res.partner",
                    "field_description": self.env._("Contact"),
                    "copied": True,
                    "tracking": model_vals.get("is_mail_thread"),
                }
            )
        )
        model_vals["field_id"].append(
            Command.create(
                {
                    "name": "x_studio_partner_phone",
                    "ttype": "many2many",
                    "relation": "phone.number",
                    "related": "x_studio_partner_id.phone_ids",
                    "store": False,
                    "field_description": self.env._("Phone"),
                }
            )
        )
        model_vals["field_id"].append(
            Command.create(
                {
                    "name": "x_studio_partner_email",
                    "ttype": "char",
                    "related": "x_studio_partner_id.email",
                    "field_description": self.env._("Email"),
                }
            )
        )

    def _create_option_use_company(self, model_vals) -> None:
        model_vals["field_id"].append(
            Command.create(
                {
                    "name": "x_studio_company_id",
                    "ttype": "many2one",
                    "relation": "res.company",
                    "field_description": self.env._("Company"),
                    "copied": True,
                    "tracking": model_vals.get("is_mail_thread"),
                }
            )
        )

    def _post_create_option_use_company(self, _model) -> None:
        # generate default for each company (note: also done when creating a new company)
        self.env["ir.access"].create(
            {
                "name": "%s - Multi-Company" % self.name,
                "model_id": self.id,
                "group_id": self.env.ref("base.group_everyone").id,
                "kind": "guard",
                "guard_scope": "everyone",
                "operation": "crud",
                "domain": "['|', ('x_studio_company_id', '=', False), ('x_studio_company_id', 'in', company_ids)]",
            }
        )
        for company in self.env["res.company"].sudo().search([]):
            self.env["ir.default"].set(
                self.model, "x_studio_company_id", company.id, company_id=company.id
            )

    def _create_option_use_notes(self, model_vals) -> None:
        model_vals["field_id"].append(
            Command.create(
                {
                    "name": "x_studio_notes",
                    "ttype": "html",
                    "field_description": self.env._("Notes"),
                    "copied": True,
                }
            )
        )

    def _create_option_use_date(self, model_vals) -> None:
        model_vals["field_id"].append(
            Command.create(
                {
                    "name": "x_studio_date",
                    "ttype": "date",
                    "field_description": self.env._("Date"),
                    "copied": True,
                }
            )
        )

    def _create_option_use_double_dates(self, model_vals) -> None:
        model_vals["field_id"].append(
            Command.create(
                {
                    "name": "x_studio_date_stop",
                    "ttype": "datetime",
                    "field_description": self.env._("End Date"),
                    "copied": True,
                }
            )
        )
        model_vals["field_id"].append(
            Command.create(
                {
                    "name": "x_studio_date_start",
                    "ttype": "datetime",
                    "field_description": self.env._("Start Date"),
                    "copied": True,
                }
            )
        )

    def _create_option_use_value(self, model_vals) -> None:
        model_vals["field_id"].append(
            Command.create(
                {
                    "name": "x_studio_currency_id",
                    "ttype": "many2one",
                    "relation": "res.currency",
                    "field_description": self.env._("Currency"),
                    "copied": True,
                }
            )
        )
        model_vals["field_id"].append(
            Command.create(
                {
                    "name": "x_studio_value",
                    "ttype": "monetary",
                    "currency_field": "x_studio_currency_id",
                    "field_description": self.env._("Value"),
                    "copied": True,
                    "tracking": model_vals.get("is_mail_thread"),
                }
            )
        )

    def _post_create_option_use_value(self, _model) -> None:
        for company in self.env["res.company"].sudo().search([]):
            self.env["ir.default"].set(
                self.model,
                "x_studio_currency_id",
                company.currency_id.id,
                company_id=company.id,
            )

    def _create_option_use_image(self, model_vals) -> None:
        model_vals["field_id"].append(
            Command.create(
                {
                    "name": "x_studio_image",
                    "ttype": "binary",
                    "field_description": self.env._("Image"),
                    "copied": True,
                }
            )
        )

    def _create_option_use_stages(self, model_vals):
        # 1. Create the stage model
        stage_model_vals = {
            "name": "%s Stages" % model_vals.get("name"),
            "model": "%s_stage" % model_vals.get("model"),
            "field_id": [
                Command.create(
                    {
                        "name": "x_name",
                        "ttype": "char",
                        "required": True,
                        "field_description": self.env._("Stage Name"),
                        "translate": "standard",
                        "copied": True,
                    }
                )
            ],
        }
        self._create_option_use_sequence(stage_model_vals)

        # 2. Link our model with the stage model
        model_vals["field_id"].extend(
            [
                Command.create(
                    {
                        "name": "x_studio_stage_id",
                        "ttype": "many2one",
                        "relation": stage_model_vals["model"],
                        "on_delete": "restrict",
                        "required": True,
                        "field_description": self.env._("Stage"),
                        "tracking": model_vals.get("is_mail_thread"),
                        "copied": True,
                        "group_expand": True,
                    }
                ),
                Command.create(
                    {
                        "name": "x_studio_priority",
                        "ttype": "boolean",
                        "field_description": self.env._("High Priority"),
                        "copied": True,
                    }
                ),
                Command.create(
                    {
                        "name": "x_color",
                        "ttype": "integer",
                        "field_description": self.env._("Color"),
                    }
                ),
                Command.create(
                    {
                        "name": "x_studio_kanban_state",
                        "ttype": "selection",
                        "selection_ids": [
                            Command.create(
                                {
                                    "value": "normal",
                                    "name": self.env._("In Progress"),
                                    "sequence": 10,
                                }
                            ),
                            Command.create(
                                {
                                    "value": "done",
                                    "name": self.env._("Ready"),
                                    "sequence": 20,
                                }
                            ),
                            Command.create(
                                {
                                    "value": "blocked",
                                    "name": self.env._("Blocked"),
                                    "sequence": 30,
                                }
                            ),
                        ],
                        "field_description": self.env._("Kanban State"),
                        "copied": True,
                    }
                ),
            ]
        )
        model_vals["order"] = "id asc"
        return stage_model_vals

    def _post_create_option_use_stages(self, stage_model) -> None:
        # create stage 'New','In Progress','Done' and set 'New' as default
        stages = self.env[stage_model.model].create(
            [
                {"x_name": self.env._("New")},
                {"x_name": self.env._("In Progress")},
                {"x_name": self.env._("Done")},
            ]
        )
        self.env["ir.default"].set(self.model, "x_studio_stage_id", stages[0].id)

    def _create_option_use_tags(self, model_vals):
        # 1. Create the tag model
        tag_model_vals = {
            "name": "%s Tags" % model_vals.get("name"),
            "model": "%s_tag" % model_vals.get("model"),
            "field_id": [
                Command.create(
                    {
                        "name": "x_name",
                        "ttype": "char",
                        "required": True,
                        "field_description": self.env._("Name"),
                        "copied": True,
                    }
                ),
                Command.create(
                    {
                        "name": "x_color",
                        "ttype": "integer",
                        "field_description": self.env._("Color"),
                        "copied": True,
                    }
                ),
            ],
        }
        # 2. Link our model with the tag model
        model_vals["field_id"].append(
            Command.create(
                {
                    "name": "x_studio_tag_ids",
                    "ttype": "many2many",
                    "relation": tag_model_vals["model"],
                    "field_description": self.env._("Tags"),
                    "relation_table": "%s_tag_rel" % model_vals.get("model"),
                    "column1": "%s_id" % model_vals.get("model"),
                    "column2": "x_tag_id",
                    "copied": True,
                }
            )
        )
        return tag_model_vals

    def _setup_access_rights(self) -> bool:
        for model in self:
            # Give all access to the created model to Employees by default, except deletion. All access to System
            # Note: a better solution may be to create groups at the app creation but the model is created
            # before the app and for other models we need to have info about the app.
            self.env["ir.access"].create(
                [
                    {
                        "name": model.name + " group_system",
                        "model_id": model.id,
                        "group_id": self.env.ref("base.group_system").id,
                        "kind": "permission",
                        "operation": "crud",
                    },
                    {
                        "name": model.name + " group_user",
                        "model_id": model.id,
                        "group_id": self.env.ref("base.group_user").id,
                        "kind": "permission",
                        "operation": "cru",
                    },
                ]
            )
        return True

    def _acquire_default_view(
        self, view_type: str, view_id: int | Literal[False] = False, create: bool = True
    ) -> IrUiView:
        """Get the default view for a given model.

        By default, create a view if one does not exist.
        """
        self.check_singleton()
        View = self.env["ir.ui.view"]
        # If we have no view_id to inherit from, it's because we are adding
        # fields to the default view of a new model. We will materialize the
        # default view as a true view so we can keep using our xpath mechanism.
        if view_id:
            view = View.browse(view_id)
        elif create:
            arch = self.env[self.model].get_view(view_id, view_type)["arch"]
            # set sample data when activating a pivot/graph view through studio
            if view_type in ["graph", "pivot"]:
                sample_view_arch = ET.fromstring(arch)  # noqa: S314  the arch get_view rendered, not uploaded XML
                sample_view_arch.set("sample", "1")
                arch = ET.tostring(sample_view_arch, encoding="unicode")
            view = View.create(
                {
                    "type": view_type,
                    "model": self.model,
                    "arch": arch,
                    "name": self.env._(
                        "Default %(view_type)s view for %(model)s",
                        view_type=view_type,
                        model=self,
                    ),
                }
            )
        else:
            view = View.browse(View.default_view(self.model, view_type))
        return view

    def _create_default_action(self, name):
        """Create an ir.act_window record set up with the available view types set up."""
        self.check_singleton()
        model_views = self.env["ir.ui.view"].search_read(
            [("model", "=", self.model), ("type", "!=", "search")], fields=["type"]
        )
        available_view_types = {v["type"] for v in model_views}
        # in actions, kanban should be first, then list, etc.
        # this is arbitrary, but we need consistency!
        VIEWS_ORDER = {
            "kanban": 0,
            "list": 1,
            "form": 2,
            "calendar": 3,
            "gantt": 4,
            "map": 5,
            "pivot": 6,
            "graph": 7,
            "qweb": 8,
            "activity": 9,
        }
        sorted_view_types = sorted(
            available_view_types, key=lambda vt: VIEWS_ORDER.get(vt, 10)
        )
        view_mode = ",".join(sorted_view_types) if sorted_view_types else "list,form"
        return self.env["ir.actions.act_window"].create(
            {
                "name": name,
                "res_model": self.model,
                "view_mode": view_mode,
                "help": self.env._("""
                <p class="o_view_nocontent_smiling_face">
                    This is your new action.
                </p>
                <p>By default, it contains a list and a form view and possibly
                    other view types depending on the options you chose for your model.
                </p>
                <p>
                    You can start customizing these screens by clicking on the Studio icon on the
                    top right corner (you can also customize this help message there).
                </p>
            """),
            }
        )

    @api.model
    def studio_model_infos(self, model_name):
        irModel = self._get(model_name)
        res = irModel.read(
            ["id", "name", "state", "is_mail_thread", "is_mail_activity", "model"]
        )[0]
        domain = []
        if model_name == "account.move":
            domain = [["move_type", "!=", "entry"]]
        res["record_ids"] = self.env[model_name].search(domain, limit=10).ids
        res["domain"] = domain
        return res


class IrModelFields(models.Model):
    _name = "ir.model.fields"
    _inherit = ["mixin.studio", "ir.model.fields"]

    @property
    def _rec_names_search(self):
        if self.env.context.get("studio"):
            return ["name", "field_description", "model", "model_id.name"]
        return ["field_description"]

    @api.depends("field_description", "model_id")
    @api.depends_context("studio")
    def _compute_display_name(self):
        if not self.env.context.get("studio"):
            return super()._compute_display_name()
        for field in self:
            field.display_name = f"{field.field_description} ({field.model_id.name})"
        return None

    @api.constrains("name")
    def _check_name(self) -> None:
        super()._check_name()
        for field in self:
            if "__" in field.name:
                raise ValidationError(
                    self.env._("Custom field names cannot contain double underscores.")
                )

    @api.model
    def _get_next_relation(self, model_name, comodel_name):
        """Prevent using the same m2m relation table when adding the same field.

        If the same m2m field was already added on the model, the user is in fact
        trying to add another relation - not the same one. We need to create another
        relation table.
        """
        result = super()._get_custom_many2many_names(model_name, comodel_name)[0]
        # check if there's already a m2m field from model_name to comodel_name;
        # if yes, check the relation table and add a sequence to it - we want to
        # be able to mirror these fields on the other side in the same order
        base = result
        attempt = 0
        existing_m2m = self.search(
            [
                ("model", "=", model_name),
                ("relation", "=", comodel_name),
                ("relation_table", "=", result),
            ]
        )
        while existing_m2m:
            attempt += 1
            result = "%s_%s" % (base, attempt)
            existing_m2m = self.search(
                [
                    ("model", "=", model_name),
                    ("relation", "=", comodel_name),
                    ("relation_table", "=", result),
                ]
            )
        return result

    @api.model
    def _get_related_field(self, model_name, related_chain_string):
        return next(
            reversed(self._get_related_field_chain(model_name, related_chain_string)),
            None,
        )

    @api.model
    def _get_related_field_chain(self, model_name, related_chain_string):
        fields = []
        for part in related_chain_string.split("."):
            model = self.env.get(model_name)
            field = None
            if model is not None:
                field = model._fields.get(part)
                if field:
                    fields.append(field)
                    model_name = field.comodel_name
            if field is None:
                return []
        return fields


class IrAccess(models.Model):
    _name = "ir.access"
    _inherit = ["mixin.studio", "ir.access"]
