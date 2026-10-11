import logging
import re
from ast import literal_eval

from odoo import api, fields, models
from odoo.exceptions import RedirectWarning, UserError, ValidationError

_logger = logging.getLogger(__name__)


class WizardWhatsappMessageSend(models.TransientModel):
    _name = "wizard.whatsapp.message.send"
    _description = "Send WhatsApp Wizard"

    def _raise_no_template_error(self, res_model) -> None:
        if self.env.user.has_group("whatsapp.group_whatsapp_admin"):
            raise RedirectWarning(
                self.env._(
                    "No approved WhatsApp Templates are available for this model."
                ),
                self.env.ref("whatsapp.whatsapp_template_action").id,
                self.env._("Configure Templates"),
                {"search_default_model": res_model},
            )
        raise ValidationError(
            self.env._("No approved WhatsApp Templates are available for this model.")
        )

    @api.model
    def default_get(self, fields):
        result = super().default_get(fields)
        context = self.env.context
        if context.get("active_model"):
            result["res_model"] = context["active_model"]
            wa_template_id = self.env["whatsapp.template"]._find_default_for_model(
                result["res_model"]
            )
            if wa_template_id and not result.get("wa_template_id"):
                result["wa_template_id"] = wa_template_id.id
            elif not wa_template_id and not result.get("wa_template_id"):
                self._raise_no_template_error(result["res_model"])

        if context.get("active_ids") or context.get("active_id"):
            result["res_ids"] = context.get("active_ids") or [context.get("active_id")]
        if context.get("active_ids") and len(context["active_ids"]) > 1:
            result["batch_mode"] = True
        return result

    attachment_id = fields.Many2one(
        comodel_name="ir.attachment",
        index=True,
    )
    res_ids = fields.Char(
        string="Document IDs",
        required=True,
    )
    res_model = fields.Char(
        string="Document Model Name",
        required=True,
    )
    batch_mode = fields.Boolean(string="Is Multiple Records")

    phone = fields.Char(
        compute="_compute_number",
        compute_sudo=False,
        store=True,
        readonly=False,
    )
    invalid_phone_number_count = fields.Integer(
        compute="_compute_invalid_phone_number_count"
    )
    wa_template_id = fields.Many2one(
        comodel_name="whatsapp.template",
        string="Template",
    )
    preview_whatsapp = fields.Html(
        string="Message Preview",
        compute="_compute_preview_whatsapp",
    )

    number_of_free_text = fields.Integer(
        string="Number of free text",
        compute="_compute_number_of_free_text",
    )
    number_of_free_text_button = fields.Integer(
        string="Number of free text Buttons",
        compute="_compute_number_of_free_text_button",
    )
    is_header_free_text = fields.Boolean(compute="_compute_is_header_free_text")
    is_button_dynamic = fields.Boolean(compute="_compute_is_button_dynamic")
    header_text_1 = fields.Char(
        string="Header Free Text",
        compute="_compute_free_text",
        store=True,
        readonly=False,
    )
    free_text_1 = fields.Char(
        compute="_compute_free_text",
        store=True,
        readonly=False,
    )
    free_text_2 = fields.Char(
        compute="_compute_free_text",
        store=True,
        readonly=False,
    )
    free_text_3 = fields.Char(
        compute="_compute_free_text",
        store=True,
        readonly=False,
    )
    free_text_4 = fields.Char(
        compute="_compute_free_text",
        store=True,
        readonly=False,
    )
    free_text_5 = fields.Char(
        compute="_compute_free_text",
        store=True,
        readonly=False,
    )
    free_text_6 = fields.Char(
        compute="_compute_free_text",
        store=True,
        readonly=False,
    )
    free_text_7 = fields.Char(
        compute="_compute_free_text",
        store=True,
        readonly=False,
    )
    free_text_8 = fields.Char(
        compute="_compute_free_text",
        store=True,
        readonly=False,
    )
    free_text_9 = fields.Char(
        compute="_compute_free_text",
        store=True,
        readonly=False,
    )
    free_text_10 = fields.Char(
        compute="_compute_free_text",
        store=True,
        readonly=False,
    )
    button_dynamic_url_1 = fields.Char(
        string="Button Url 1",
        compute="_compute_button_dynamic_url",
        store=True,
        readonly=False,
    )
    button_dynamic_url_2 = fields.Char(
        string="Button Url 2",
        compute="_compute_button_dynamic_url",
        store=True,
        readonly=False,
    )


    @api.depends("wa_template_id")
    def _compute_number(self) -> None:
        for composer in self:
            records = self.env[composer.res_model].browse(
                literal_eval(composer.res_ids)
            )
            numbers = []
            for record in records[:12]:
                if composer.wa_template_id.phone_field:
                    try:
                        numbers.append(
                            record._whatsapp_phone_resolve(
                                composer.wa_template_id.phone_field
                            )[0]
                        )
                    except UserError as err:
                        error_msg = self.env._(
                            "Template %(template_name)s holds a wrong configuration for 'phone field'\n%(error_msg)s",
                            template_name=composer.wa_template_id.name,
                            error_msg=err.args[0],
                        )
                        raise ValidationError(error_msg) from err
            if not composer.batch_mode:
                phone = self.env.context.get("default_phone")
                if not phone:
                    phone = numbers[0] if numbers and numbers[0] else composer.phone
            elif not numbers:
                phone = False
            else:
                other_count = len(records) - len(numbers)
                phone = ", ".join(self._extract_digits(num) for num in numbers if num)
                if other_count:
                    phone += self.env._(", ... (%s Others)", other_count)
            composer.phone = phone

    @api.depends("phone", "batch_mode")
    def _compute_invalid_phone_number_count(self) -> None:
        for composer in self:
            records = self._get_active_records()
            if composer.batch_mode:
                invalid_phone_number_count = 0
                for rec in records:
                    mobile_number = rec._whatsapp_phone_format(
                        fpath=composer.wa_template_id.phone_field
                    )
                    if not mobile_number:
                        invalid_phone_number_count += 1
            elif composer.phone:
                sanitize_number = records._whatsapp_phone_format(number=composer.phone)
                invalid_phone_number_count = 1 if not sanitize_number else 0
            else:
                invalid_phone_number_count = 1
            composer.invalid_phone_number_count = invalid_phone_number_count

    @api.depends(lambda self: self._get_fields_free_text())
    def _compute_preview_whatsapp(self) -> None:
        for record in self:
            rec = record._get_active_records()
            if record.wa_template_id and rec:
                record.preview_whatsapp = self.env["ir.qweb"]._render(
                    "whatsapp.template_message_preview",
                    {
                        "body": record._get_html_preview_whatsapp(rec=rec[0]),
                        "buttons": record.wa_template_id.button_ids,
                        "header_type": record.wa_template_id.header_type,
                        "footer_text": record.wa_template_id.footer_text,
                        "language_direction": "rtl"
                        if record.wa_template_id.lang_code in ("ar", "he", "fa", "ur")
                        else "ltr",
                    },
                )
            else:
                record.preview_whatsapp = None

    @api.depends("wa_template_id")
    def _compute_number_of_free_text_button(self) -> None:
        for rec in self:
            tmpl_vars = rec.wa_template_id.variable_ids
            rec.number_of_free_text_button = len(
                tmpl_vars.filtered(
                    lambda var: (
                        var.field_type == "free_text" and var.line_type == "button"
                    )
                )
            )

    @api.depends("wa_template_id")
    def _compute_number_of_free_text(self) -> None:
        for rec in self:
            if rec.wa_template_id:
                rec.number_of_free_text = len(
                    rec.wa_template_id.variable_ids.filtered(
                        lambda line: (
                            line.field_type == "free_text" and line.line_type == "body"
                        )
                    )
                )
            else:
                rec.number_of_free_text = 0

    @api.depends("wa_template_id")
    def _compute_is_header_free_text(self) -> None:
        for rec in self:
            if (
                rec.wa_template_id
                and rec.wa_template_id.variable_ids
                and rec.wa_template_id.variable_ids.filtered(
                    lambda line: (
                        line.field_type == "free_text" and line.line_type == "header"
                    )
                )
            ):
                rec.is_header_free_text = True
            else:
                rec.is_header_free_text = False

    @api.depends("wa_template_id")
    def _compute_is_button_dynamic(self) -> None:
        for rec in self:
            if (
                rec.wa_template_id
                and rec.wa_template_id.variable_ids
                and rec.wa_template_id.variable_ids.filtered(
                    lambda line: (
                        line.field_type == "free_text" and line.line_type == "button"
                    )
                )
            ):
                rec.is_button_dynamic = True
            else:
                rec.is_button_dynamic = False

    @api.depends("wa_template_id")
    def _compute_button_dynamic_url(self) -> None:
        for rec in self:
            freetext_btn_vars = rec.wa_template_id.variable_ids.filtered(
                lambda line: (
                    line.line_type == "button" and line.field_type == "free_text"
                )
            )
            freetext_btn_vars = freetext_btn_vars.sorted(
                key=lambda var: var.button_id.sequence
            )
            rec.button_dynamic_url_1 = (
                freetext_btn_vars[0].demo_value if len(freetext_btn_vars) > 0 else False
            )
            rec.button_dynamic_url_2 = (
                freetext_btn_vars[1].demo_value if len(freetext_btn_vars) > 1 else False
            )

    @api.depends("wa_template_id")
    def _compute_free_text(self) -> None:
        for rec in self:
            header_text = False
            free_texts = []
            if rec.wa_template_id.header_type == "text":
                header_param = rec.wa_template_id.variable_ids.filtered(
                    lambda line: (
                        line.line_type == "header" and line.field_type == "free_text"
                    )
                )
                if header_param:
                    header_text = header_param[0].demo_value
            if rec.wa_template_id.variable_ids:
                free_texts = (
                    rec.wa_template_id.variable_ids.filtered(
                        lambda line: (
                            line.line_type == "body" and line.field_type == "free_text"
                        )
                    )
                    .sorted(key=lambda var: var._extract_variable_index())
                    .mapped("demo_value")
                )
            rec.header_text_1 = header_text
            for index in range(1, 11):
                rec[f"free_text_{index}"] = (
                    free_texts[index - 1] if index <= len(free_texts) else False
                )

    def _extract_digits(self, string):
        if not string:
            return string
        matches = re.findall(r"\d+", string)
        return "".join(matches)

    def _get_fields_free_text(self):
        return [
            "wa_template_id",
            "header_text_1",
            "button_dynamic_url_1",
            "button_dynamic_url_2",
        ] + [f"free_text_{i}" for i in range(1, 11)]


    def action_send_whatsapp_template(self):
        self.check_singleton()
        if not self.wa_template_id:
            raise ValidationError(
                self.env._("Please select a WhatsApp Template to send.")
            )
        return self._send_whatsapp_template()

    def _create_whatsapp_messages(self, force_create=False):
        records = self._get_active_records()

        if self.wa_template_id and self.wa_template_id.variable_ids:
            field_types = self.wa_template_id.variable_ids.mapped("field_type")
            if "user_phone" in field_types and not self.env.user._phone_get_number():
                raise ValidationError(
                    self.env._(
                        "User phone number required in template but no value set on user profile."
                    )
                )
        free_text_json = self._get_text_free_json()
        message_vals_all = []
        raise_exception = not (self.batch_mode or force_create)
        for rec in records:
            mobile_number = None
            if self.batch_mode:
                formatted_number_wa = rec._whatsapp_phone_format(
                    fpath=self.wa_template_id.phone_field,
                    raise_on_format_error=raise_exception,
                )
                mobile_number = rec._whatsapp_phone_resolve(
                    self.wa_template_id.phone_field
                )[0]
            elif not mobile_number:
                mobile_number = self.phone
                formatted_number_wa = rec._whatsapp_phone_format(
                    number=mobile_number,
                    raise_on_format_error=raise_exception,
                )

            message_vals = {}

            if not formatted_number_wa:
                message_vals.update(
                    {
                        "failure_type": "phone_invalid",
                        "state": "error",
                    }
                )

            body = self._get_html_preview_whatsapp(rec=rec)
            post_values = {
                "attachment_ids": [self.attachment_id.id] if self.attachment_id else [],
                "body": body,
                "message_type": "whatsapp_message",
                "partner_ids": rec._mail_get_partners()[rec.id].ids
                or rec._whatsapp_get_responsible().partner_id.ids,
            }
            if self.res_model == "discuss.channel":
                message = rec.message_post(
                    body=body, message_type="comment", subtype_xmlid="mail.mt_comment"
                )
            elif hasattr(records, "_message_log"):
                message = rec._message_log(**post_values)
            else:
                message = self.env["mail.message"].create(
                    dict(
                        post_values,
                        res_id=rec.id,
                        model=self.res_model,
                        subtype_id=self.env["ir.model.data"]._xmlid_to_res_id(
                            "mail.mt_note"
                        ),
                    )
                )
            message_vals_all.append(
                message_vals
                | {
                    "mail_message_id": message.id,
                    "mobile_number": mobile_number,
                    "mobile_number_formatted": formatted_number_wa,
                    "free_text_json": free_text_json,
                    "wa_template_id": self.wa_template_id.id,
                    "wa_account_id": self.wa_template_id.wa_account_id.id,
                }
            )
        if message_vals_all:
            return self.env["whatsapp.message"].create(message_vals_all)
        return self.env["whatsapp.message"]

    def _send_whatsapp_template(self, force_send_by_cron=False):
        messages = self._create_whatsapp_messages(force_create=force_send_by_cron)
        if messages:
            messages._send(force_send_by_cron=force_send_by_cron)
            return messages
        return self.env["whatsapp.message"]

    def _get_text_free_json(self):
        self.check_singleton()
        json_vals = {}
        if self.header_text_1:
            json_vals["header_text"] = self.header_text_1
        if self.number_of_free_text:
            free_text_field = [
                f"free_text_{i + 1}" for i in range(self.number_of_free_text)
            ]
            for value in free_text_field:
                if self[value]:
                    json_vals[value] = self[value]
        if self.button_dynamic_url_1:
            json_vals["button_dynamic_url_1"] = self.button_dynamic_url_1
        if self.button_dynamic_url_2:
            json_vals["button_dynamic_url_2"] = self.button_dynamic_url_2
        return json_vals

    def _get_html_preview_whatsapp(self, rec):
        self.check_singleton()
        template_variables_value = (
            self.wa_template_id.variable_ids._get_variables_value(rec)
        )
        text_vars = self.wa_template_id.variable_ids.filtered(
            lambda var: var.field_type == "free_text"
        )
        body_text_vars = text_vars.filtered(lambda var: var.line_type == "body").sorted(
            key=lambda var: var._extract_variable_index()
        )
        for var_index, body_text_var in zip(
            range(1, self.number_of_free_text + 1), body_text_vars, strict=False
        ):
            free_text_x = self[f"free_text_{var_index}"]
            if free_text_x:
                template_variables_value[f"body-{body_text_var.name}"] = free_text_x
        if self.header_text_1 and text_vars.filtered(
            lambda var: var.line_type == "header"
        ):
            template_variables_value["header-{{1}}"] = self.header_text_1
        return self.wa_template_id._get_formatted_body(
            variable_values=template_variables_value
        )


    def _get_active_records(self):
        self.check_singleton()
        return self.env[self.res_model].browse(literal_eval(self.res_ids))
