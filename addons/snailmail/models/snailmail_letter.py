import base64
import io
import re
from typing import TYPE_CHECKING

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Frame, KeepInFrame, Paragraph

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import iap
from odoo.tools.pdf import BrandedFileWriter, PdfReader
from odoo.tools.safe_eval import safe_eval

if TYPE_CHECKING:
    from odoo.addons.base.models.ir_attachment import IrAttachment

DEFAULT_ENDPOINT = "https://iap-snailmail.odoo.com"
PRINT_ENDPOINT = "/iap/snailmail/1/print"
DEFAULT_TIMEOUT = 30

ERROR_CODES = [
    "MISSING_REQUIRED_FIELDS",
    "CREDIT_ERROR",
    "TRIAL_ERROR",
    "NO_PRICE_AVAILABLE",
    "FORMAT_ERROR",
    "UNKNOWN_ERROR",
    "ATTACHMENT_ERROR",
]


class SnailmailLetter(models.Model):
    _name = "snailmail.letter"
    _description = "Snailmail Letter"

    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Sent by",
    )
    model = fields.Char(required=True)
    res_id = fields.Integer(
        string="Document ID",
        required=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Recipient",
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company.id,
        readonly=True,
        required=True,
    )
    report_template = fields.Many2one(
        comodel_name="ir.actions.report",
        string="Optional report to print and attach",
    )

    attachment_id = fields.Many2one(
        comodel_name="ir.attachment",
        index="btree_not_null",
        ondelete="cascade",
    )
    attachment_datas = fields.Binary(
        related="attachment_id.datas",
        string="Document",
    )
    attachment_fname = fields.Char(
        related="attachment_id.name",
        string="Attachment Filename",
    )
    color = fields.Boolean(
        default=lambda self: self.env.company.snailmail_config_id.snailmail_color
    )
    cover = fields.Boolean(
        string="Cover Page",
        default=lambda self: self.env.company.snailmail_config_id.snailmail_cover,
    )
    duplex = fields.Boolean(
        string="Both side",
        default=lambda self: self.env.company.snailmail_config_id.snailmail_duplex,
    )
    state = fields.Selection(
        selection=[
            ("pending", "In Queue"),
            ("sent", "Sent"),
            ("error", "Error"),
            ("canceled", "Cancelled"),
        ],
        string="Status",
        default="pending",
        copy=False,
        readonly=True,
        required=True,
        help="When a letter is created, the status is 'Pending'.\n"
        "If the letter is correctly sent, the status goes in 'Sent',\n"
        "If not, it will got in state 'Error' and the error message will be displayed in the field 'Error Message'.",
    )
    error_code = fields.Selection(
        selection=[(err_code, err_code) for err_code in ERROR_CODES],
        string="Error",
    )
    info_msg = fields.Html(string="Information")

    reference = fields.Char(
        string="Related Record",
        compute="_compute_reference",
        store=False,
        readonly=True,
    )

    message_id = fields.Many2one(
        comodel_name="mail.message",
        string="Snailmail Status Message",
        index="btree_not_null",
    )
    notification_ids = fields.One2many(
        comodel_name="mail.notification",
        inverse_name="letter_id",
        string="Notifications",
    )

    street = fields.Char()
    street2 = fields.Char()
    zip = fields.Char()
    city = fields.Char()
    state_id = fields.Many2one(comodel_name="res.country.state")
    country_id = fields.Many2one(comodel_name="res.country")

    @api.depends("attachment_id", "partner_id")
    def _compute_display_name(self):
        for letter in self:
            if letter.attachment_id:
                letter.display_name = (
                    f"{letter.attachment_id.name} - {letter.partner_id.name}"
                )
            else:
                letter.display_name = letter.partner_id.name

    @api.depends("model", "res_id")
    def _compute_reference(self) -> None:
        for res in self:
            res.reference = "%s,%s" % (res.model, res.res_id)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            msg_id = (
                self.env[vals["model"]]
                .browse(vals["res_id"])
                .message_post(
                    body=self.env._("Letter sent by post with Snailmail"),
                    message_type="snailmail",
                )
            )

            partner_id = self.env["res.partner"].browse(vals["partner_id"])
            vals.update(
                {
                    "message_id": msg_id.id,
                    "street": partner_id.street,
                    "street2": partner_id.street2,
                    "zip": partner_id.zip,
                    "city": partner_id.city,
                    "state_id": partner_id.state_id.id,
                    "country_id": partner_id.country_id.id,
                }
            )
        letters = super().create(vals_list)

        notification_vals = [
            {
                "author_id": letter.message_id.author_id.id,
                "mail_message_id": letter.message_id.id,
                "res_partner_id": letter.partner_id.id,
                "notification_type": "snail",
                "letter_id": letter.id,
                "is_read": True,
                "notification_status": "ready",
            }
            for letter in letters
        ]

        self.env["mail.notification"].sudo().create(notification_vals)

        letters.attachment_id.check_access("read")
        return letters

    def write(self, vals):
        res = super().write(vals)
        if "attachment_id" in vals:
            self.attachment_id.check_access("read")
        return res

    def _generate_report_pdf(self, report):
        obj = self.env[self.model].browse(self.res_id)
        if report.print_report_name:
            report_name = safe_eval(report.print_report_name, {"object": obj})
        elif report.attachment:
            report_name = safe_eval(report.attachment, {"object": obj})
        else:
            report_name = "Document"
        filename = "%s.%s" % (report_name, "pdf")
        pdf_bin = (
            self.env["ir.actions.report"]
            .with_context(snailmail_layout=not self.cover, lang="en_US")
            ._render_qweb_pdf(report, self.res_id)[0]
        )
        return filename, pdf_bin

    def _acquire_attachment(self) -> IrAttachment:
        self.check_singleton()
        if not self.attachment_id:
            report = self.report_template
            if not report:
                report_name = self.env.context.get("report_name")
                report = self.env["ir.actions.report"]._get_report_from_name(
                    report_name
                )
                if not report:
                    return self.env["ir.attachment"]
                else:
                    self.write({"report_template": report.id})
            paperformat = report.get_paperformat()
            if (
                paperformat.format == "custom"
                and paperformat.page_width != 210
                and paperformat.page_height != 297
            ) or paperformat.format != "A4":
                raise UserError(self.env._("Please use an A4 Paper format."))
            prev = self.company_id.report_config_id.external_report_layout_id
            if prev in {
                self.env.ref(f"web.external_layout_{layout}")
                for layout in ("bubble", "wave", "folder")
            }:
                self.company_id.report_config_id.external_report_layout_id = (
                    self.env.ref("web.external_layout_standard")
                )
            try:
                filename, pdf_bin = self._generate_report_pdf(report)
            finally:
                self.company_id.report_config_id.external_report_layout_id = prev

            pdf_bin = self._overwrite_margins(pdf_bin)
            if self.cover:
                pdf_bin = self._add_cover_page(pdf_bin)
            attachment = self.env["ir.attachment"].create(
                {
                    "name": filename,
                    "datas": base64.b64encode(pdf_bin),
                    "res_model": "snailmail.letter",
                    "res_id": self.id,
                    "type": "binary",
                }
            )
            self.write({"attachment_id": attachment.id})

        return self.attachment_id

    def _count_pages_pdf(self, bin_pdf):
        pages = 0
        for match in re.compile(rb"/Count\s+(\d+)").finditer(bin_pdf):
            pages = int(match.group(1))
        return pages

    def _snailmail_create(self, route) -> dict:
        account_token = (
            self.env["iap.account"].acquire_account("snailmail").sudo().account_token
        )
        dbuuid = self.env.registry.settings.get(self.env, "database.uuid", False)
        documents = []

        for letter in self:
            recipient_name = letter.partner_id.name or (
                letter.partner_id.parent_id and letter.partner_id.parent_id.name
            )
            if not recipient_name:
                letter.write(
                    {
                        "info_msg": self.env._("Invalid recipient name."),
                        "state": "error",
                        "error_code": "MISSING_REQUIRED_FIELDS",
                    }
                )
                continue
            document = {
                "letter_id": letter.id,
                "res_model": letter.model,
                "res_id": letter.res_id,
                "contact_address": letter.partner_id.with_context(
                    snailmail_layout=True, show_address=True
                ).display_name,
                "address": {
                    "name": recipient_name,
                    "street": letter.partner_id.street,
                    "street2": letter.partner_id.street2,
                    "zip": letter.partner_id.zip,
                    "state": letter.partner_id.state_id.code
                    if letter.partner_id.state_id
                    else False,
                    "city": letter.partner_id.city,
                    "country_code": letter.partner_id.country_id.code,
                },
                "return_address": {
                    "name": letter.company_id.partner_id.name,
                    "street": letter.company_id.partner_id.street,
                    "street2": letter.company_id.partner_id.street2,
                    "zip": letter.company_id.partner_id.zip,
                    "state": letter.company_id.partner_id.state_id.code
                    if letter.company_id.partner_id.state_id
                    else False,
                    "city": letter.company_id.partner_id.city,
                    "country_code": letter.company_id.partner_id.country_id.code,
                },
            }
            if route == "estimate":
                document.update(pages=1)
            else:
                document.update(
                    {
                        "company_logo": (
                            letter.company_id.logo_web
                            and letter.company_id.logo_web.decode("utf-8")
                        )
                        or False,
                    }
                )
                attachment = letter._acquire_attachment()
                if attachment:
                    document.update(
                        {
                            "pdf_bin": route == "print"
                            and attachment.datas.decode("utf-8"),
                            "pages": route == "estimate"
                            and self._count_pages_pdf(
                                base64.b64decode(attachment.datas)
                            ),
                        }
                    )
                else:
                    letter.write(
                        {
                            "info_msg": "The attachment could not be generated.",
                            "state": "error",
                            "error_code": "ATTACHMENT_ERROR",
                        }
                    )
                    continue
                if (
                    letter.company_id.report_config_id.external_report_layout_id
                    == self.env.ref("l10n_de.external_layout_din5008", False)
                ):
                    document.update(
                        {
                            "rightaddress": 0,
                        }
                    )
            documents.append(document)

        return {
            "account_token": account_token,
            "dbuuid": dbuuid,
            "documents": documents,
            "options": {
                "color": self and self[0].color,
                "cover": self and self[0].cover,
                "duplex": self and self[0].duplex,
                "currency_name": "EUR",
            },
            "batch": True,
        }

    def _get_error_message(self, error):
        if error == "CREDIT_ERROR":
            link = self.env["iap.account"].get_credits_url(service_name="snailmail")
            return self.env._(
                'You don\'t have enough credits to perform this operation.<br>Please go to your <a href=%s target="new">iap account</a>.',
                link,
            )
        if error == "TRIAL_ERROR":
            link = self.env["iap.account"].get_credits_url(service_name="snailmail")
            return self.env._(
                'You don\'t have an IAP account registered for this service.<br>Please go to <a href=%s target="new">iap.odoo.com</a> to claim your free credits.',
                link,
            )
        if error == "NO_PRICE_AVAILABLE":
            return self.env._("The country of the partner is not covered by Snailmail.")
        if error == "MISSING_REQUIRED_FIELDS":
            return self.env._("One or more required fields are empty.")
        if error == "FORMAT_ERROR":
            return self.env._(
                "The attachment of the letter could not be sent. Please check its content and contact the support if the problem persists."
            )
        else:
            return self.env._("An unknown error happened. Please contact the support.")
        return error

    def _get_failure_type(self, error) -> str:
        if error == "CREDIT_ERROR":
            return "sn_credit"
        if error == "TRIAL_ERROR":
            return "sn_trial"
        if error == "NO_PRICE_AVAILABLE":
            return "sn_price"
        if error == "MISSING_REQUIRED_FIELDS":
            return "sn_fields"
        if error == "FORMAT_ERROR":
            return "sn_format"
        else:
            return "sn_error"

    def _snailmail_print(self, immediate=True) -> None:
        valid_address_letters = self.filtered(lambda l: l._is_valid_address(l))
        invalid_address_letters = self - valid_address_letters
        invalid_address_letters._snailmail_print_invalid_address()
        if valid_address_letters and immediate:
            for letter in valid_address_letters:
                letter._snailmail_print_valid_address()
                self.env["ir.cron"]._commit_progress()

    def _snailmail_print_invalid_address(self) -> None:
        error = "MISSING_REQUIRED_FIELDS"
        error_message = self.env._("The address of the recipient is not complete")
        self.write(
            {
                "state": "error",
                "error_code": error,
                "info_msg": error_message,
            }
        )
        self.notification_ids.sudo().write(
            {
                "notification_status": "exception",
                "failure_type": self._get_failure_type(error),
                "failure_reason": error_message,
            }
        )
        self.message_id._notify_message_notification_update()

    def _snailmail_print_valid_address(self) -> None:
        endpoint = self.env.registry.settings.get(
            self.env, "snailmail.endpoint", DEFAULT_ENDPOINT
        )
        timeout = int(
            self.env.registry.settings.get(
                self.env, "snailmail.timeout", DEFAULT_TIMEOUT
            )
        )
        params = self._snailmail_create("print")
        try:
            response = iap.jsonrpc(
                endpoint + PRINT_ENDPOINT, params=params, timeout=timeout, env=self.env
            )
        except AccessError:
            for doc in params["documents"]:
                letter = self.browse(doc["letter_id"])
                letter.state = "error"
                letter.error_code = "UNKNOWN_ERROR"
            raise
        for doc in response["request"]["documents"]:
            if doc.get("sent") and response["request_code"] == 200:
                self.env["iap.account"]._send_success_notification(
                    message=self.env._("Snail Mails are successfully sent")
                )
                note = self.env._(
                    "The document was correctly sent by post.<br>The tracking id is %s",
                    doc["send_id"],
                )
                letter_data = {"info_msg": note, "state": "sent", "error_code": False}
                notification_data = {
                    "notification_status": "sent",
                    "failure_type": False,
                    "failure_reason": False,
                }
            else:
                error = (
                    doc["error"]
                    if response["request_code"] == 200
                    else response["reason"]
                )

                if error == "CREDIT_ERROR":
                    self.env["iap.account"]._send_no_credit_notification(
                        service_name="snailmail",
                        title=self.env._("Not enough credits for Snail Mail"),
                    )
                note = self.env._(
                    "An error occurred when sending the document by post.<br>Error: %s",
                    self._get_error_message(error),
                )
                letter_data = {
                    "info_msg": note,
                    "state": "error",
                    "error_code": error if error in ERROR_CODES else "UNKNOWN_ERROR",
                }
                notification_data = {
                    "notification_status": "exception",
                    "failure_type": self._get_failure_type(error),
                    "failure_reason": note,
                }

            letter = self.browse(doc["letter_id"])
            letter.write(letter_data)
            letter.notification_ids.sudo().write(notification_data)
        self.message_id._notify_message_notification_update()

    def snailmail_print(self) -> None:
        self.write({"state": "pending"})
        self.notification_ids.sudo().write(
            {
                "notification_status": "ready",
                "failure_type": False,
                "failure_reason": False,
            }
        )
        self.message_id._notify_message_notification_update()
        if len(self) == 1:
            self._snailmail_print()

    def cancel(self):
        self.write({"state": "canceled", "error_code": False})
        self.notification_ids.sudo().write(
            {
                "notification_status": "canceled",
            }
        )
        self.message_id._notify_message_notification_update()

    @api.model
    def _snailmail_cron(self, autocommit=True) -> None:
        letters_send = self.search(
            [
                "|",
                ("state", "=", "pending"),
                "&",
                ("state", "=", "error"),
                (
                    "error_code",
                    "in",
                    [
                        "TRIAL_ERROR",
                        "CREDIT_ERROR",
                        "ATTACHMENT_ERROR",
                        "MISSING_REQUIRED_FIELDS",
                    ],
                ),
            ]
        )
        for letter in letters_send:
            letter._snailmail_print()
            if letter.error_code == "CREDIT_ERROR":
                break
            if autocommit:
                self.env["ir.cron"]._commit_progress()

    @api.model
    def _is_valid_address(self, record) -> bool:
        record.check_singleton()
        required_keys = ["street", "city", "zip", "country_id"]
        return all(record[key] for key in required_keys)

    def _get_cover_address_split(self):
        address_split = self.partner_id.with_context(
            show_address=True, lang="en_US"
        ).display_name.split("\n")
        if self.country_id.code == "DE":
            if self.street2:
                address_split[1] = f"{self.street} // {self.street2}"
            address_split[2] = f"{self.zip} {self.city}"
        return address_split

    def _add_cover_page(self, invoice_bin: bytes):
        out_writer = BrandedFileWriter()
        address_split = self._get_cover_address_split()
        address_split[0] = (
            self.partner_id.name
            or (self.partner_id.parent_id and self.partner_id.parent_id.name)
            or address_split[0]
        )
        address = "<br/>".join(address_split)
        address_x = 118 * mm
        address_y = 60 * mm
        frame_width = 85.5 * mm
        frame_height = 25.5 * mm

        cover_buf = io.BytesIO()
        canvas = Canvas(cover_buf, pagesize=A4)
        styles = getSampleStyleSheet()

        frame = Frame(
            address_x, A4[1] - address_y - frame_height, frame_width, frame_height
        )
        story = [Paragraph(address, styles["Normal"])]
        address_inframe = KeepInFrame(0, 0, story)
        frame.addFromList([address_inframe], canvas)
        canvas.save()
        cover_buf.seek(0)

        invoice = PdfReader(io.BytesIO(invoice_bin))
        cover_bin = io.BytesIO(cover_buf.getvalue())
        cover_file = PdfReader(cover_bin)
        out_writer.append_pages_from_reader(cover_file)

        if self.duplex:
            out_writer.add_blank_page()

        out_writer.append_pages_from_reader(invoice)

        out_buff = io.BytesIO()
        out_writer.write(out_buff)
        return out_buff.getvalue()

    def _overwrite_margins(self, invoice_bin: bytes):
        pdf_buf = io.BytesIO()
        canvas = Canvas(pdf_buf, pagesize=A4)
        canvas.setFillColorRGB(1, 1, 1)
        page_width = A4[0]
        page_height = A4[1]

        hmargin_width = page_width
        hmargin_height = 5 * mm

        vmargin_width = 5 * mm
        vmargin_height = page_height

        sq_width = 15 * mm

        canvas.rect(0, 0, hmargin_width, hmargin_height, stroke=0, fill=1)
        canvas.rect(0, page_height, hmargin_width, -hmargin_height, stroke=0, fill=1)

        canvas.rect(0, 0, vmargin_width, vmargin_height, stroke=0, fill=1)
        canvas.rect(page_width, 0, -vmargin_width, vmargin_height, stroke=0, fill=1)

        canvas.rect(0, 0, sq_width, sq_width, stroke=0, fill=1)
        canvas.save()
        pdf_buf.seek(0)

        new_pdf = PdfReader(pdf_buf)
        curr_pdf = PdfReader(io.BytesIO(invoice_bin))
        out = BrandedFileWriter()
        for page in curr_pdf.pages:
            out.add_page(page)
            added_page = out.pages[-1]
            added_page.merge_page(new_pdf.pages[0])
            added_page.compress_content_streams()
        out_stream = io.BytesIO()
        out.write(out_stream)
        out_bin = out_stream.getvalue()
        out_stream.close()
        return out_bin
