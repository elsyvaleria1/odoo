from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_date


class WizardSignRequestSend(models.TransientModel):
    _name = "wizard.sign.request.send"
    _description = "Sign send request"

    def _selection_target_model(self):
        return [
            (model.model, model.name)
            for model in self.env["ir.model"]
            .sudo()
            .search(
                [
                    ("model", "!=", "sign.request"),
                    ("is_mail_thread", "=", "True"),
                ]
            )
        ]

    activity_id = fields.Many2one(
        comodel_name="mail.activity",
        string="Linked Activity",
        readonly=True,
    )
    reference_doc = fields.Reference(
        selection="_selection_target_model",
        string="Linked to",
        readonly=True,
    )
    has_default_template = fields.Boolean()
    available_template_ids = fields.Many2many(
        comodel_name="sign.template",
        compute="_compute_available_template_ids",
    )
    template_id = fields.Many2one(
        comodel_name="sign.template",
        string="Sign Template",
        ondelete="cascade",
    )

    signer_ids = fields.One2many(
        comodel_name="wizard.sign.request.send.signer",
        inverse_name="sign_send_request_id",
        string="Signers",
        compute="_compute_signer_ids",
        store=True,
    )
    set_sign_order = fields.Boolean(
        string="Signing Order",
        help="""Specify the order for each signer. The signature request only gets sent to \
                                    the next signers in the sequence when all signers from the previous level have \
                                    signed the document.
                                    """,
    )
    signer_id = fields.Many2one(
        comodel_name="res.partner",
        string="Send To",
    )
    signers_count = fields.Count(count_of="signer_ids")
    cc_partner_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Copy to",
        help="Contacts in copy will be notified by email once the document is either fully signed or refused.",
    )
    is_user_signer = fields.Boolean(compute="_compute_is_user_signer")

    subject = fields.Char(
        compute="_compute_subject",
        store=True,
        readonly=False,
    )
    body = fields.Html(
        string="body",
        compute="_compute_mail_message_body",
        store=True,
        readonly=False,
        help="Message to be sent to signers of the specified document",
    )
    message_cc = fields.Html(
        string="CC Message",
        help="Message to be sent to contacts in copy of the signed document",
    )
    attachment_ids = fields.Many2many(
        comodel_name="ir.attachment",
        string="Attachments",
        bypass_search_access=True,
    )
    filename = fields.Char(
        compute="_compute_filename",
        store=True,
    )

    validity = fields.Date(
        string="Valid Until",
        compute="_compute_validity",
        store=True,
        readonly=False,
        help="Leave empty for requests without expiration.",
    )
    reminder_enabled = fields.Boolean(default=False)
    reminder = fields.Integer(default=7)
    certificate_reference = fields.Boolean(
        default=False,
        help="If checked, the unique certificate reference will be added on the final signed document.",
    )
    model = fields.Char(string="Related Document Model")
    res_ids = fields.Text(string="Related Document IDs")
    scheduled_date = fields.Char()

    only_autofill_readonly = fields.Boolean(
        string="Only Autofill",
        compute="_compute_only_autofill_readonly",
    )
    display_download_button = fields.Boolean(
        compute="_compute_display_download_button",
        store=False,
    )

    @api.constrains("validity")
    def _check_validity(self):
        if any(wiz.validity and wiz.validity < fields.Date.today() for wiz in self):
            raise UserError(
                self.env._("Request expiration date must be set in the future.")
            )

    @api.onchange("reminder")
    def _onchange_reminder(self) -> None:
        self.reminder = min(self.reminder, 365)

    def _get_default_signer(self):
        if self.reference_doc or self.env.context.get("default_reference_doc"):
            ref = self.reference_doc
            if ref._name == "res.partner":
                return ref.id

            partner = "partner_id" in ref and ref.partner_id
            if partner:
                return partner.id

            user = "user_id" in ref and ref.user_id
            if user and user.partner_id:
                return user.partner_id.id

            employee = "employee_id" in ref and ref.employee_id
            if employee and employee.partner_id:
                return employee.partner_id.id

        return self.env.context.get("default_signer_id", self.env.user.partner_id.id)

    @api.depends("template_id", "set_sign_order", "template_id.sign_item_ids")
    def _compute_signer_ids(self) -> None:
        for wiz in self:
            default_signer = wiz._get_default_signer()
            template = wiz.template_id
            roles = template.sign_item_ids.responsible_id.sorted()
            signer_ids = []
            if wiz.signer_ids and len(wiz.signer_ids) == len(roles):
                all_default = all(
                    signer.mail_sent_order == 1 for signer in wiz.signer_ids
                )
                for default_signing_order, signer in enumerate(wiz.signer_ids):
                    if wiz.set_sign_order:
                        mail_sent_order = (
                            default_signing_order + 1
                            if all_default
                            else signer.mail_sent_order
                        )
                    else:
                        mail_sent_order = 1
                    signer_ids.append(
                        (
                            0,
                            0,
                            {
                                "role_id": signer.role_id.id,
                                "partner_id": signer.partner_id.id,
                                "mail_sent_order": mail_sent_order,
                            },
                        )
                    )
            else:
                for default_signing_order, role in enumerate(roles):
                    if default_signing_order == 0:
                        partner_id = (
                            role.assign_to.id if role.assign_to else default_signer
                        )
                    else:
                        partner_id = role.assign_to.id if role.assign_to else False
                    signer_vals = {
                        "role_id": role.id,
                        "partner_id": partner_id,
                        "mail_sent_order": default_signing_order + 1
                        if wiz.set_sign_order
                        else 1,
                    }
                    signer_ids.append((0, 0, signer_vals))
            wiz.signer_ids = [Command.clear()] + signer_ids

    @api.depends("template_id", "reference_doc")
    def _compute_display_name(self):
        for wiz in self:
            display_name = self.env._("Sign Request ")
            if wiz.reference_doc:
                display_name = self.env._(
                    "Sign Request - %s", wiz.reference_doc.display_name
                )
            wiz.display_name = display_name

    @api.depends("template_id", "reference_doc")
    def _compute_subject(self) -> None:
        for wiz in self:
            subject = self.env._("Signature Request")
            if wiz.reference_doc:
                subject = self.env._(
                    "Signature Request - %(template_name)s - %(res_name)s",
                    template_name=wiz.template_id.display_name,
                    res_name=wiz.reference_doc.display_name or "",
                )
            elif wiz.template_id:
                subject = self.env._(
                    "Signature Request - %(file_name)s", file_name=wiz.template_id.name
                )
            wiz.subject = subject

    @api.depends("template_id", "reference_doc")
    def _compute_filename(self) -> None:
        for wiz in self:
            filename = self.env._("Sign Request")
            if wiz.reference_doc:
                filename = self.env._(
                    "Sign Request - %s", wiz.reference_doc.display_name
                )
            elif wiz.template_id:
                filename = wiz.template_id.display_name
            wiz.filename = filename

    @api.depends("template_id")
    def _compute_validity(self) -> None:
        for wiz in self:
            if wiz.template_id:
                if wiz.template_id.signature_request_validity:
                    wiz.validity = fields.Date.today() + relativedelta(
                        days=wiz.template_id.signature_request_validity
                    )
                else:
                    wiz.validity = None

    @api.depends("signer_ids.partner_id", "signer_id", "signers_count")
    def _compute_is_user_signer(self) -> None:
        partner = self.env.user.partner_id
        for wiz in self:
            wiz.is_user_signer = (
                partner in wiz.signer_ids.partner_id
                if wiz.signers_count
                else partner == wiz.signer_id
            )

    @api.depends("reference_doc")
    def _compute_available_template_ids(self) -> None:
        non_specific_templates = (
            self.env["sign.template"]
            .search([("model_id", "=", False)])
            ._filtered_access("read")
        )
        template_by_model = {}
        if self.reference_doc:
            model_names = [
                ref._name for ref in self.reference_doc if self.reference_doc
            ]
            model_ids = (
                self.env["ir.model"].sudo().search([("model", "in", model_names)]).ids
            )
            res = self.env["sign.template"]._read_group(
                [("model_id", "in", model_ids)],
                groupby=["model_id"],
                aggregates=["id:recordset"],
            )
            for model, template in res:
                template_by_model[model.id] = template
        for wiz in self:
            all_template_ids = non_specific_templates.ids
            if wiz.reference_doc:
                model = self.env["ir.model"].sudo()._get(wiz.reference_doc._name)
                other_templates = template_by_model.get(
                    model.id, self.env["sign.template"]
                )
                all_template_ids += other_templates.ids
            wiz.available_template_ids = [Command.set(all_template_ids)]

    @api.depends("template_id")
    def _compute_mail_message_body(self) -> None:
        for wiz in self:
            if wiz.template_id:
                wiz.body = wiz.template_id.message


    def _activity_done(self) -> None:
        signatories = self.signer_id.name or self.signer_ids.partner_id.mapped("name")
        feedback = self.env._(
            "Signature requested for template: %(template)s\nSignatories: %(signatories)s",
            template=self.template_id.name,
            signatories=signatories,
        )
        self.activity_id._action_done(feedback=feedback)

    def create_request(self):
        send_channel = self.env.context.get("send_channel", "email")
        template_id = self.template_id.id
        if self.signers_count:
            signers = [
                {
                    "partner_id": signer.partner_id.id,
                    "role_id": signer.role_id.id,
                    "mail_sent_order": signer.mail_sent_order,
                }
                for signer in self.signer_ids
            ]
        else:
            signers = [
                {
                    "partner_id": self.signer_id.id,
                    "role_id": self.env.ref("sign.sign_item_role_default").id,
                    "mail_sent_order": 1,
                }
            ]
        cc_partner_ids = self.cc_partner_ids.ids
        reference = self.filename or self.template_id.name
        subject = self.subject
        message = self.body
        message_cc = self.message_cc
        attachment_ids = self.attachment_ids
        scheduled_date = self.scheduled_date or False
        reference_doc = None
        if self.reference_doc:
            reference_doc = f"{self.reference_doc._name},{self.reference_doc.id}"
        sign_request = (
            self.env["sign.request"]
            .with_context(scheduled_date=scheduled_date)
            .create(
                {
                    "template_id": template_id,
                    "request_item_ids": [
                        Command.create(
                            {
                                "partner_id": signer["partner_id"],
                                "role_id": signer["role_id"],
                                "mail_sent_order": signer["mail_sent_order"],
                            }
                        )
                        for signer in signers
                    ],
                    "reference": reference,
                    "subject": subject,
                    "message": message,
                    "message_cc": message_cc,
                    "attachment_ids": [Command.set(attachment_ids.ids)],
                    "validity": self.validity,
                    "reminder": self.reminder,
                    "reminder_enabled": self.reminder_enabled,
                    "reference_doc": reference_doc,
                    "certificate_reference": self.certificate_reference,
                    "send_channel": send_channel,
                }
            )
        )
        sign_request.message_subscribe(partner_ids=cc_partner_ids)
        return sign_request

    def _create_log_and_close(self, request):
        self._create_request_log_note(request)
        if self.activity_id:
            self._activity_done()

        if not self.reference_doc:
            return self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
                "sign.sign_request_action"
            )

        next_action = request.get_close_values().get("action")

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": self.env._("Request sent successfully"),
                "next": next_action
                or {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }

    def send_request(self):
        self.check_singleton()
        request = self.create_request()
        return self._create_log_and_close(request)

    def _create_request_log_note(self, request) -> None:
        if request.reference_doc:
            model = self.env["ir.model"]._get(request.reference_doc._name)
            if model.is_mail_thread:
                body = self.env._(
                    "A signature request has been linked to this document: %s",
                    request._get_html_link(),
                )
                request.reference_doc.message_post(body=body)
                body = self.env._(
                    "%s has been linked to this sign request.",
                    request.reference_doc._get_html_link(),
                )
                request.message_post(body=body)

    def sign_directly(self):
        self.check_singleton()
        request = self.create_request()
        if self.activity_id:
            self._activity_done()
        if self.env.context.get("sign_all"):
            return request.go_to_signable_document(request.request_item_ids)
        return request.go_to_signable_document()

    @api.depends("template_id", "signer_ids")
    def _compute_only_autofill_readonly(self) -> None:
        item_type_to_field = {
            "signature": "sign_signature",
            "initial": "sign_initials",
        }
        date_type = self.env.ref("sign.sign_item_type_date")
        for wiz in self:
            role_to_user_map = {
                signer.role_id.id: signer.partner_id.main_user_id
                for signer in wiz.signer_ids
            }
            item_auto_fill_values = []
            for item in wiz.template_id.sign_item_ids:
                user = role_to_user_map.get(item.responsible_id.id)
                res = False
                constant_item = (
                    item.constant
                    or item.type_id.sudo().auto_field
                    or item.type_id == date_type
                )
                if constant_item:
                    res = True
                elif (
                    item.type_id.item_type in item_type_to_field
                    and user == self.env.user
                ):
                    sign_field = item_type_to_field[item.type_id.item_type]
                    res = bool(user[sign_field])
                item_auto_fill_values.append(res)
            wiz.only_autofill_readonly = all(item_auto_fill_values)

    @api.depends("only_autofill_readonly", "signers_count", "is_user_signer")
    def _compute_display_download_button(self) -> None:
        for wiz in self:
            wiz.display_download_button = (
                wiz.only_autofill_readonly
                and (wiz.signers_count == 1)
                and wiz.is_user_signer
            )

    def quick_sign(self):
        request = self.create_request()

        date_type = self.env.ref("sign.sign_item_type_date")
        request_item = request.request_item_ids
        sign_request_item = request_item.sudo()
        corrected_dict = {}
        frames = {}
        for item in self.template_id.sign_item_ids:
            key = str(item.id)
            item_type = item.type_id.sudo()
            if item.constant:
                corrected_dict[key] = request_item._get_constant_value(item)
            elif item_type.auto_field:
                corrected_dict[key] = request_item._get_auto_field_value(
                    {"id": item_type.id, "auto_field": item_type.auto_field}
                )
            elif item_type.item_type in ("signature", "initial"):
                signature_field_name = (
                    "sign_signature"
                    if item_type.item_type == "signature"
                    else "sign_initials"
                )
                user_signature = sign_request_item._get_user_signature(
                    signature_field_name
                )
                user_signature_frame = sign_request_item._get_user_signature_frame(
                    signature_field_name + "_frame"
                )
                corrected_dict[key] = (
                    "data:image/png;base64,%s" % user_signature.decode()
                    if user_signature
                    else False
                )
                frames[key] = {
                    "frameValue": "data:image/png;base64,%s"
                    % user_signature_frame.decode()
                    if user_signature_frame
                    else False,
                    "frameHash": False,
                }
            elif item_type == date_type:
                corrected_dict[key] = format_date(self.env, fields.Date.today())
            else:
                corrected_dict[key] = item.name

        sign_request_item._sign(corrected_dict, frame=frames)

        url = f"/sign/download/{request.id}/{request.access_token}/completed"
        if self.reference_doc:
            view_record = self.reference_doc
            action = {
                "type": "ir.actions.client",
                "tag": "sign_download_document_and_return",
                "params": {
                    "url": url,
                    "res_model": view_record._name,
                    "res_id": view_record.id,
                    "view_mode": "form",
                },
            }
        else:
            action = {
                "type": "ir.actions.client",
                "tag": "sign_download_document_and_return",
                "params": {"url": url, "redirect_to": "sign.sign_request_action"},
            }
        return action
