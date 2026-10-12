from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.libs.web import urljoin as url_join
from odoo.tools import frozendict


class WhatsappTemplateVariable(models.Model):
    _name = "whatsapp.template.variable"
    _description = "WhatsApp Template Variable"
    _order = "line_type desc, name, id"
    _access_anchors = frozendict(
        {
            "company": "wa_template_id.wa_account_id.allowed_company_ids",
            "owner": models.Anchor("wa_template_id.allowed_user_ids", shared=True),
        }
    )

    name = fields.Char(
        string="Placeholder",
        required=True,
    )
    button_id = fields.Many2one(
        comodel_name="whatsapp.template.button",
        index="btree_not_null",
        ondelete="cascade",
    )
    wa_template_id = fields.Many2one(
        comodel_name="whatsapp.template",
        index=True,
        required=True,
        ondelete="cascade",
    )
    model = fields.Char(
        related="wa_template_id.model",
        string="Model Name",
    )

    line_type = fields.Selection(
        selection=[
            ("button", "Button"),
            ("header", "Header"),
            ("location", "Location"),
            ("body", "Body"),
        ],
        string="Variable location",
        required=True,
    )
    field_type = fields.Selection(
        selection=[
            ("user_name", "User Name"),
            ("user_phone", "User Phone"),
            ("free_text", "Free Text"),
            ("portal_url", "Portal Link"),
            ("field", "Field of Model"),
        ],
        string="Type",
        default="free_text",
        required=True,
    )
    field_name = fields.Char(string="Field")
    demo_value = fields.Char(
        string="Sample Value",
        default="Sample Value",
        required=True,
    )

    _name_type_template_unique = models.Constraint(
        "UNIQUE(name, line_type, wa_template_id, button_id)",
        "Variable names must be unique for a given template",
    )

    @api.constrains("field_type", "demo_value", "button_id")
    def _check_demo_values(self) -> None:
        if self.filtered(
            lambda var: var.field_type == "free_text" and not var.demo_value
        ):
            raise ValidationError(
                self.env._("Free Text template variables must have a demo value.")
            )

    @api.constrains("field_type", "field_name")
    def _check_field_name(self) -> None:
        is_system = self.env.user.has_group("base.group_system")
        failing = self.browse()
        to_check = self.filtered(lambda v: v.field_type == "field")
        missing = to_check.filtered(lambda v: not v.field_name)
        if missing:
            raise ValidationError(
                self.env._(
                    "Field template variables %(var_names)s must be associated with a field.",
                    var_names=", ".join(missing.mapped("name")),
                )
            )
        for variable in to_check:
            model = self.env[variable.model]
            if not is_system:
                if not model.has_access("read"):
                    model_description = (
                        self.env["ir.model"]._get(variable.model).display_name
                    )
                    raise ValidationError(
                        self.env._(
                            "You can not select field of %(model)s.",
                            model=model_description,
                        )
                    )
                safe_fields = (
                    model._get_fields_whatsapp_safe()
                    if hasattr(model, "_get_fields_whatsapp_safe")
                    else []
                )
                if variable.field_name not in safe_fields:
                    raise ValidationError(
                        self.env._(
                            "You are not allowed to use field %(field)s, contact your administrator.",
                            field=variable.field_name,
                        )
                    )
            try:
                model._mail_get_field_path_value(variable.field_name)
            except UserError:
                failing += variable
        if failing:
            model_description = (
                self.env["ir.model"]._get(failing.mapped("model")[0]).display_name
            )
            raise ValidationError(
                self.env._(
                    "Variables %(field_names)s do not seem to be valid field path for model %(model_name)s.",
                    field_names=", ".join(failing.mapped("field_name")),
                    model_name=model_description,
                )
            )

    @api.constrains("name")
    def _check_name(self) -> None:
        for variable in self:
            if variable.line_type == "location" and variable.name not in {
                "name",
                "address",
                "latitude",
                "longitude",
            }:
                raise ValidationError(
                    self.env._(
                        "Location variable should be 'name', 'address', 'latitude' or 'longitude'. Cannot parse '%(placeholder)s'",
                        placeholder=variable.name,
                    )
                )
            if (
                variable.line_type == "button"
                and variable.name != variable.button_id.name
            ):
                raise ValidationError(
                    self.env._(
                        "Dynamic button variable name must be the same as its respective button's name"
                    )
                )
            if (
                variable.line_type in ("header", "body")
                and not variable._extract_variable_index()
            ):
                raise ValidationError(
                    self.env._(
                        'Template variable should be in format {{number}}. Cannot parse "%(placeholder)s"',
                        placeholder=variable.name,
                    )
                )

    @api.constrains("button_id", "line_type")
    def _check_button_id(self) -> None:
        for variable in self:
            if variable.line_type == "button" and not variable.button_id:
                raise ValidationError(
                    self.env._("Button variables must be linked to a button.")
                )

    @api.depends("line_type", "name")
    def _compute_display_name(self):
        type_names = dict(self._fields["line_type"]._description_selection(self.env))
        for variable in self:
            type_name = type_names[variable.line_type or "body"]
            variable.display_name = (
                type_name
                if variable.line_type == "header"
                else f"{type_name} - {variable.name}"
            )

    @api.onchange("model")
    def _onchange_model_id(self):
        self.field_name = False

    @api.onchange("field_type")
    def _onchange_field_type(self) -> None:
        if self.field_type != "field":
            self.field_name = False

    def _get_variables_value(self, record):
        value_by_name = {}
        user = self.env.user
        for variable in self:
            if variable.field_type == "user_name":
                value = user.name
            elif variable.field_type == "user_phone":
                value = user._phone_get_number().number
            elif variable.field_type == "field":
                value = variable._find_value_from_field_chain(record)
            elif variable.field_type == "portal_url":
                portal_url = record._whatsapp_get_portal_url()
                value = url_join(variable.get_base_url(), (portal_url or ""))
            else:
                value = variable.demo_value

            value_str = (value and str(value)) or ""
            if variable.button_id:
                value_by_name[f"button-{variable.button_id.name}"] = value_str
            else:
                value_by_name[f"{variable.line_type}-{variable.name}"] = value_str

        return value_by_name

    def _find_value_from_field_chain(self, record):
        self.check_singleton()
        return self._resolve_field_path_value(record.sudo(False))

    def _resolve_field_path_value(self, record):
        self.check_singleton()
        last_model_path, _dot, last_fname = self.field_name.rpartition(".")
        try:
            last_model = record.mapped(last_model_path) if last_model_path else record
            last_field = last_model._fields.get(last_fname)
        except KeyError, AttributeError, ValueError:
            last_field = None
        if (
            last_field is not None
            and last_field.type == "many2many"
            and last_field.comodel_name == "phone.number"
        ):
            return (
                last_model.mapped(last_fname)._primary("whatsapp", "mobile").number
                or ""
            )
        return record._mail_get_field_path_value(self.field_name)

    def _extract_variable_index(self) -> int | None:
        self.check_singleton()
        try:
            return int(self.name.removeprefix("{{").removesuffix("}}"))
        except ValueError:
            return None
