import base64
import binascii
import contextlib
from datetime import datetime
from itertools import chain
from xml.etree import (
    ElementTree,  # noqa: ICN001  used as `ElementTree` throughout this module
)

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class DocumentsDocument(models.Model):
    _inherit = "document.document"

    # once we parsed the XML to know if a PDF is embedded inside,
    # we store that information so we don't need to parse it again
    has_embedded_pdf = fields.Boolean(
        string="Has Embedded PDF",
        compute="_compute_has_embedded_pdf",
        store=True,
    )

    @api.depends("has_embedded_pdf")
    def _compute_thumbnail_source_checksum(self) -> None:
        super()._compute_thumbnail_source_checksum()

    def _get_thumbnail_kind(self) -> str | bool:
        # an XML invoice carrying a PDF shows that PDF, as a PDF file would
        if self.has_embedded_pdf:
            if self.attachment_id.type == "cloud_storage":
                return "browser"
            return "pdf"
        return super()._get_thumbnail_kind()

    def _get_thumbnail_source(self) -> bytes:
        if self.has_embedded_pdf:
            return self._extract_pdf_from_xml() or b""
        return super()._get_thumbnail_source()

    @api.depends("checksum")
    def _compute_has_embedded_pdf(self) -> None:
        for document in self:
            document.has_embedded_pdf = bool(document._extract_pdf_from_xml())

    def _extract_pdf_from_xml(self):
        """Parse the XML file and return the PDF content if one is found.

        For some invoice files (in the XML format), we can have a PDF embedded inside
        in base 64. We want to be able to preview it in documents.

        We support the UBL format
        > https://docs.peppol.eu/poacc/billing/3.0/syntax/ubl-invoice
        """
        self.check_singleton()

        if not self.mimetype:
            _debug.logic("embedded_pdf_skipped", reason="no_mimetype", document=self)
            return False

        if not (
            self.mimetype.endswith("/xml")
            or (self.mimetype == "text/plain" and self.name.lower().endswith(".xml"))
        ):
            _debug.logic(
                "embedded_pdf_skipped", reason="not_xml", mimetype=self.mimetype
            )
            return False

        raw = self.with_context(bin_size=False).raw
        if not raw:
            # An attachment whose bytes live in cloud storage reads as False
            # here rather than as an empty string, and there is nothing to
            # search for an embedded PDF in.
            _debug.logic("embedded_pdf_skipped", reason="no_raw", document=self)
            return False
        try:
            xml_file_content = raw.decode()
        except UnicodeDecodeError:
            _debug.logic("embedded_pdf_skipped", reason="not_utf8", document=self)
            return False

        # quick filters, to not parse the XML most of the cases
        if (
            "EmbeddedDocumentBinaryObject" not in xml_file_content
            and "Attachment" not in xml_file_content
        ):
            _debug.logic("embedded_pdf_skipped", reason="no_marker", document=self)
            return False

        try:
            tree = ElementTree.fromstring(xml_file_content)  # noqa: S314  ElementTree resolves no external entity, and expat caps entity expansion
        except ElementTree.ParseError:
            _debug.logic("embedded_pdf_skipped", reason="unparseable", document=self)
            return False

        attachment_nodes = tree.iterfind(".//{*}EmbeddedDocumentBinaryObject")
        attachment_nodes = chain(attachment_nodes, tree.iterfind(".//{*}Attachment"))

        for attachment_node in attachment_nodes:
            if len(attachment_node):  # the node has children
                continue

            with contextlib.suppress(TypeError, binascii.Error):
                # check file header in case many file are embedded in the XML
                if (
                    pdf_attachment_content := base64.b64decode(
                        attachment_node.text + "===="
                    )
                ).startswith(b"%PDF-"):
                    _debug.logic("embedded_pdf_found", document=self)
                    return pdf_attachment_content

        _debug.logic("embedded_pdf_skipped", reason="no_pdf_node", document=self)
        return False

    def _is_in_journal_folder(self) -> bool:
        """Whether this document sits in a folder some journal syncs into.

        A document there was filed by the journal synchronization and follows
        the journal; one anywhere else was filed on purpose and stays put.
        """
        self.check_singleton()
        if not self.folder_id:
            return False
        return bool(
            self.env["document.account.folder.setting"]
            .sudo()
            .search_count([("folder_id", "=", self.folder_id.id)], limit=1)
        )

    def account_create_account_move(
        self, move_type, journal_id=None, partner_id=None, skip_activities=False
    ):
        if not skip_activities:
            for record in self:
                record.activity_ids.action_feedback(feedback="completed")
        if any(document.type == "folder" for document in self):
            _debug.logic("move_create_refused", reason="folder", documents=self)
            raise UserError(self.env._("You can not create account move on folder."))

        if journal_id is None:
            company_journals = self.env["account.journal"].search(
                [
                    *self.env["account.journal"]._check_company_domain(
                        self.env.company
                    ),
                ]
            )
            if move_type == "statement":
                journal_id = company_journals.filtered(
                    lambda journal: journal.type == "bank"
                )[:1]
            else:
                journal_id = self.env["account.move"]._get_suitable_journal_ids(
                    move_type
                )[:1]
        elif isinstance(journal_id, int):
            journal_id = self.env["account.journal"].browse(journal_id)

        _debug.pipeline(
            "account_move_create",
            documents=self,
            move_type=move_type,
            journal=journal_id,
        )
        move = None
        invoices = self.env["account.move"]

        # 'entry' is handled outside the document loop because the returned
        # actions can differ (cf. l10n_be_soda)
        if move_type == "entry":
            _debug.logic("account_move_create", by="entry_batch", documents=self)
            return journal_id.create_document_from_attachment(
                attachment_ids=self.attachment_id.ids
            )

        for document in self:
            partner = partner_id or document.partner_id
            if document.res_model == "account.move" and document.res_id:
                _debug.logic("account_move", by="existing_link", document=document)
                move = self.env["account.move"].browse(document.res_id)
            else:
                creation_context = {"default_move_type": move_type}
                if (
                    move_type in ("in_invoice", "in_refund")
                    and partner
                    and "property_purchase_currency_id" in partner
                ):
                    supplier_currency = partner.with_company(
                        document.company_id
                    ).property_purchase_currency_id
                    if supplier_currency:
                        _debug.logic("supplier_currency_applied", partner=partner)
                        creation_context["default_currency_id"] = supplier_currency.id
                move = journal_id.with_context(
                    **creation_context
                )._create_document_from_attachment(
                    attachment_ids=document.attachment_id.id
                )
            if partner:
                move.partner_id = partner
            if move.statement_line_id:
                move["suspense_statement_line_id"] = move.statement_line_id.id

            invoices |= move

        _debug.lifecycle("account_moves_created", documents=self, moves=invoices)

        # When running an action on several documents, this method is called in a
        # loop (because of the "multi" server action). When it is the case, we try
        # to redirect to a list of all created invoices instead of just the last
        # one, using the context.
        context = dict(self.env.context, default_move_type=move_type)
        documents_active_ids = context.get("documents_active_ids")
        if (
            context.get("active_model") != "document.document"
            or not documents_active_ids
        ):
            invoice_ids = invoices.ids
        else:
            invoice_ids = self.browse(documents_active_ids).mapped("res_id")
        action = {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "name": self.env._("Invoices"),
            "view_id": False,
            "view_mode": "list",
            "views": [(False, "list"), (False, "form")],
            "domain": [("id", "in", invoice_ids)],
            "context": context,
        }
        if len(invoice_ids) == 1:
            record = move or invoices[0]
            view_id = record.get_formview_id() if record else False
            action.update(
                {
                    "view_mode": "form",
                    "views": [(view_id, "form")],
                    "res_id": invoice_ids[0],
                    "view_id": view_id,
                }
            )
        return action

    def account_create_account_bank_statement(self, journal_id=None):
        # It is not possible to link the doc
        # to the newly created entry as they can be more than one. But importing
        # many times the same bank statement is later checked.
        default_journal = journal_id or self.env["account.journal"].search(
            [
                *self.env["account.journal"]._check_company_domain(self.env.company),
                ("type", "=", "bank"),
            ],
            limit=1,
        )

        if not default_journal:
            _debug.logic("statement_refused", reason="no_bank_journal", documents=self)
            error_msg = self.env["account.journal"]._prepare_no_journal_error_msg(
                self.env.company.display_name, ["bank"]
            )
            raise UserError(error_msg)

        _debug.pipeline(
            "bank_statement_import", documents=self, journal=default_journal
        )
        return default_journal.create_document_from_attachment(
            attachment_ids=self.attachment_id.ids
        )

    @api.model
    def _get_domain_base_server_actions(self):
        return Domain.AND(
            [
                super()._get_domain_base_server_actions(),
                Domain.OR(
                    [
                        [("state", "!=", "documents_account_record_create")],
                        [("documents_account_journal_id", "=", False)],
                        [
                            (
                                "documents_account_journal_id.company_id",
                                "=",
                                self.env.company.id,
                            )
                        ],
                    ]
                ),
            ]
        )

    @api.model
    def _create_missing_account_documents(self) -> None:
        _debug.lifecycle("finance_folders_seeded", company=self.env.company)
        self._load_records(
            [
                {
                    "xml_id": "document.document_finance_folder",
                    "noupdate": True,
                    "values": {
                        "active": True,
                        "type": "folder",
                        "access_internal": "edit",
                        "name": self.env._("Finance"),
                        "sequence": 10,
                    },
                }
            ]
        )
        self._load_records(
            [
                {
                    "xml_id": "document.document_finance_taxes_folder",
                    "noupdate": True,
                    "values": {
                        "active": True,
                        "type": "folder",
                        "access_internal": "edit",
                        "folder_id": self.env.ref(
                            "document.document_finance_folder"
                        ).id,
                        "name": self.env._("Taxes"),
                        "sequence": 120,
                    },
                }
            ]
        )
        self._load_records(
            [
                {
                    "xml_id": "document.document_finance_annual_closing_folder",
                    "noupdate": True,
                    "values": {
                        "active": True,
                        "type": "folder",
                        "access_internal": "edit",
                        "folder_id": self.env.ref(
                            "document.document_finance_folder"
                        ).id,
                        "name": self.env._("Annual Closing"),
                        "sequence": 130,
                    },
                },
            ]
        )
        self._load_records(
            [
                {
                    "xml_id": "document.document_finance_annual_closing_year_current_folder",
                    "noupdate": True,
                    "values": {
                        "active": True,
                        "type": "folder",
                        "access_internal": "edit",
                        "folder_id": self.env.ref(
                            "document.document_finance_annual_closing_folder"
                        ).id,
                        "name": str(datetime.now().year),
                        "sequence": 200,
                    },
                },
            ]
        )

    def _get_details_panel_res_models(self) -> list[str]:
        return [*super()._get_details_panel_res_models(), "account.move"]
