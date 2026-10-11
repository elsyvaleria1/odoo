from urllib.parse import urlparse

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.libs.web import urljoin as url_join
from odoo.tools import frozendict

from odoo.addons.phone_validation.tools import phone_validation


class WhatsappTemplateButton(models.Model):
    _name = "whatsapp.template.button"
    _description = "WhatsApp Template Button"
    _order = "sequence,id"
    _access_anchors = frozendict(
        {
            "company": "wa_template_id.wa_account_id.allowed_company_ids",
            "owner": models.Anchor("wa_template_id.allowed_user_ids", shared=True),
        }
    )

    sequence = fields.Integer()
    name = fields.Char(
        string="Button Text",
        size=25,
    )
    wa_template_id = fields.Many2one(
        comodel_name="whatsapp.template",
        index=True,
        required=True,
        ondelete="cascade",
    )

    button_type = fields.Selection(
        selection=[
            ("url", "Visit Website"),
            ("phone_number", "Call Number"),
            ("quick_reply", "Quick Reply"),
        ],
        string="Type",
        default="quick_reply",
        required=True,
    )
    url_type = fields.Selection(
        selection=[("static", "Static"), ("dynamic", "Dynamic")],
        default="static",
    )
    website_url = fields.Char(string="Website URL")
    call_number = fields.Char()
    has_invalid_number = fields.Boolean(compute="_compute_has_invalid_number")
    variable_ids = fields.One2many(
        comodel_name="whatsapp.template.variable",
        inverse_name="button_id",
        compute="_compute_variable_ids",
        precompute=True,
        store=True,
        copy=True,
    )

    _unique_name_per_template = models.Constraint(
        "UNIQUE(name, wa_template_id)",
        "Button names must be unique in a given template",
    )

    @api.depends("button_type", "call_number")
    def _compute_has_invalid_number(self) -> None:
        for button in self:
            if button.button_type == "phone_number" and button.call_number:
                try:
                    phone_validation.phone_format(
                        button.call_number,
                        False,
                        False,
                    )
                except UserError:
                    if (
                        country := self.env.user.country_id
                        or self.env.company.country_id
                    ):
                        try:
                            phone_validation.phone_format(
                                button.call_number,
                                country.code,
                                country.phone_code,
                            )
                        except UserError:
                            button.has_invalid_number = True
                            continue
            button.has_invalid_number = False

    def _prepare_button_variable_vals(self, button) -> dict:
        return {
            "demo_value": button.website_url + "???",
            "line_type": "button",
            "name": button.name,
            "wa_template_id": button.wa_template_id.id,
        }

    def _filter_dynamic_buttons(self):
        return self.filtered(
            lambda button: button.button_type == "url" and button.url_type == "dynamic"
        )

    @api.depends("button_type", "url_type", "website_url", "name")
    def _compute_variable_ids(self) -> None:
        button_urls = self._filter_dynamic_buttons()
        to_clear = self - button_urls
        for button in button_urls:
            if button.variable_ids:
                button.variable_ids = [
                    Command.update(
                        button.variable_ids[0].id,
                        self._prepare_button_variable_vals(button),
                    ),
                ]
            else:
                button.variable_ids = [
                    Command.create(self._prepare_button_variable_vals(button)),
                ]
        if to_clear:
            to_clear.variable_ids = [(5, 0)]

    def check_variable_ids(self) -> None:
        for button in self:
            if len(button.variable_ids) > 1:
                raise ValidationError(
                    self.env._("Buttons may only contain one placeholder.")
                )
            if button.variable_ids and button.url_type != "dynamic":
                raise ValidationError(
                    self.env._("Only dynamic urls may have a placeholder.")
                )
            if button.url_type == "dynamic" and not button.variable_ids:
                raise ValidationError(
                    self.env._("All dynamic urls must have a placeholder.")
                )
            if button.variable_ids.name != "{{1}}":
                raise ValidationError(
                    self.env._("The placeholder for a button can only be {{1}}.")
                )

    @api.onchange("website_url")
    def _onchange_website_url(self) -> None:
        if self.website_url:
            if self.website_url.startswith("/"):
                if (base_url := self.get_base_url()) and "localhost" not in base_url:
                    self.website_url = url_join(base_url, self.website_url)
            elif (parsed_url := urlparse(self.website_url)) and not parsed_url.scheme:
                self.website_url = f"https://{self.website_url}"
