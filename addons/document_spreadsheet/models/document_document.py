import base64
import contextlib
import io
import zipfile

from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command, Domain
from odoo.libs.debug_log import DebugLog
from odoo.libs.documents import mimetype_for
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tools.image import image_process
from odoo.tools.misc import DEFAULT_SERVER_DATE_FORMAT

from odoo.addons.base.models.access_link import LinkLoginRequired, LinkRefused

SUPPORTED_PATHS = (
    "[Content_Types].xml",
    "xl/sharedStrings.xml",
    "xl/styles.xml",
    "xl/workbook.xml",
    "_rels/",
    "xl/_rels",
    "xl/charts/",
    "xl/drawings/",
    "xl/externalLinks/",
    "xl/pivotTables/",
    "xl/tables/",
    "xl/theme/",
    "xl/worksheets/",
    "xl/media",
)

XLSX_MIME_TYPES = [
    mimetype_for("xlsx"),
    "application/wps-office.xlsx",
]

_debug = DebugLog(__name__)


class DocumentsDocument(models.Model):
    _name = "document.document"
    _inherit = ["document.document", "mixin.spreadsheet"]

    spreadsheet_binary_data = fields.Binary(
        compute="_compute_spreadsheet_binary_data",
        inverse="_inverse_spreadsheet_binary_data",
        default=None,
    )
    spreadsheet_thumbnail_checksum = fields.Char(
        export_string_translation=False,
        compute="_compute_spreadsheet_thumbnail_checksum",
    )
    excel_export = fields.Binary()

    handler = fields.Selection(
        selection=[
            ("spreadsheet", "Spreadsheet"),
            ("frozen_folder", "Frozen Folder"),
            ("frozen_spreadsheet", "Frozen Spreadsheet"),
        ],
        ondelete={
            "spreadsheet": "cascade",
            "frozen_folder": "cascade",
            "frozen_spreadsheet": "cascade",
        },
    )

    _spreadsheet_access_via_link = models.Constraint(
        "CHECK((handler != 'spreadsheet') OR access_via_link != 'edit')",
        "To share a spreadsheet in edit mode, add the user in the accesses",
    )
    _frozen_spreadsheet_access_via_link = models.Constraint(
        "CHECK((handler != 'frozen_spreadsheet') OR access_via_link != 'edit')",
        "A frozen spreadsheet can not be editable",
    )

    def action_freeze_and_copy(self, spreadsheet_data, excel_files) -> dict:
        """Render the spreadsheet in JS, and then make a copy to share it.

        :param spreadsheet_data: The spreadsheet data to save
        :param excel_files: The files to download
        """
        self.check_singleton()

        # we will copy in SUDO to skip check on frozen spreadsheets
        # (see @_check_spreadsheet_share)
        self.env["document.document"].check_access("create")
        self.check_access("read")
        if (
            not self.env.su
            and self.folder_id
            and self.folder_id.user_permission != "edit"
        ):
            _debug.logic(
                "spreadsheet_freeze_denied",
                records=self,
                reason="folder_not_editable",
                folder=self.folder_id,
            )
            raise AccessError(
                self.env._("You are not allowed to freeze spreadsheets in Company")
            )

        folder_sudo = (
            self.env["document.document"]
            .sudo()
            .search(
                [
                    ("folder_id", "=", self.folder_id.id),
                    ("type", "=", "folder"),
                    ("handler", "=", "frozen_folder"),
                ],
                limit=1,
            )
        )

        _debug.logic(
            "spreadsheet_frozen_folder",
            records=self,
            folder=folder_sudo or None,
            action="reused" if folder_sudo else "created",
        )
        if not folder_sudo:
            folder_sudo = (
                self.env["document.document"]
                .sudo()
                .create(
                    {
                        "name": self.env._("Frozen spreadsheets"),
                        "type": "folder",
                        "handler": "frozen_folder",
                        "folder_id": self.folder_id.id,
                        "access_via_link": "none",
                        "access_internal": "none",
                        "access_ids": False,
                        "owner_id": False,
                    }
                )
            )

        if isinstance(spreadsheet_data, dict):
            spreadsheet_data = json_dumps(spreadsheet_data)

        document = self.sudo().copy(
            {
                "name": self.env._(
                    "Frozen at %(date)s: %(name)s",
                    date=fields.Date.today().strftime(DEFAULT_SERVER_DATE_FORMAT),
                    name=self.name,
                ),
                "access_internal": "none" if self.access_internal == "none" else "view",
                "access_via_link": "view",
                "spreadsheet_data": spreadsheet_data,
                "folder_id": folder_sudo.id,
                "excel_export": base64.b64encode(
                    self.env["mixin.spreadsheet"]._zip_xslx_files(excel_files)
                ),
                "handler": "frozen_spreadsheet",
                "is_access_via_link_hidden": True,
                # whoever reaches the spreadsheet, on it or from its folders,
                # views the frozen copy, which sits behind a boundary
                "access_ids": [
                    Command.create({"partner_id": partner.id, "role": "view"})
                    for partner in {
                        source["partner"]
                        for source in self._access_graph_sources()
                        if source["partner"]
                    }
                ],
            }
        )
        _debug.lifecycle(
            "spreadsheet_frozen",
            source=self,
            frozen=document,
            folder=folder_sudo,
            excel_files=len(excel_files),
            accesses=len(self.access_ids),
        )
        return {
            "id": document.id,
            "shortcut_document_id": document.shortcut_document_id.id,
        }

    def _get_domain_access_update(self):
        """Allow to change the access of the frozen folders / spreadsheets only if we open their share panel."""
        return super()._get_domain_access_update() & (
            Domain("id", "in", self.ids)
            | Domain("handler", "not in", ("frozen_folder", "frozen_spreadsheet"))
        )

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = self._resize_spreadsheet_thumbnails(vals_list)
        for vals in vals_list:
            if vals.get("handler") == "frozen_folder":
                # what the spreadsheet's folder grants does not reach its frozen
                # copies: the frozen folder is a boundary
                vals.setdefault("is_access_restricted", True)
        documents = super().create(vals_list)
        _debug.lifecycle("spreadsheet_create", documents=documents)
        documents._update_spreadsheet_contributors()
        return documents

    @api.model
    def _kept_from_share_editors(self):
        # a spreadsheet is edited by internal users only, whatever grant
        # reaches an external one from its folder
        return super()._kept_from_share_editors() | Domain(
            "handler", "in", ("spreadsheet", "frozen_spreadsheet")
        )

    def write(self, vals):
        if (
            "handler" not in vals
            and "mimetype" in vals
            and vals["mimetype"] != "application/o-spreadsheet"
        ):
            _debug.logic(
                "spreadsheet_handler_cleared",
                documents=self,
                mimetype=vals["mimetype"],
            )
            vals["handler"] = False
        if "spreadsheet_data" in vals:
            self._update_spreadsheet_contributors()
        if all(
            document.handler in ("spreadsheet", "frozen_spreadsheet")
            for document in self
        ):
            vals = self._resize_thumbnail_value(vals)
        return super().write(vals)

    def dispatch_spreadsheet_message(self, message, access_token=None):
        if self.sudo().handler == "frozen_spreadsheet":
            _debug.logic(
                "spreadsheet_message_ignored",
                records=self,
                reason="frozen",
                type=message.get("type"),
            )
            return False
        return super().dispatch_spreadsheet_message(message, access_token)

    def _get_serialized_spreadsheet_data_body(self, access_token=None):
        body = super()._get_serialized_spreadsheet_data_body(access_token)
        self._update_spreadsheet_contributors()
        return body

    def _get_spreadsheet_metadata(self, access_token=None):
        if self.sudo().handler not in ("spreadsheet", "frozen_spreadsheet"):
            _debug.logic(
                "spreadsheet_metadata_refused",
                records=self,
                reason="not_a_spreadsheet",
                handler=self.sudo().handler,
            )
            raise ValidationError(
                self.env._("The spreadsheet you are trying to access does not exist.")
            )
        data = super()._get_spreadsheet_metadata(access_token)
        self._update_spreadsheet_contributors()
        sudo_self = self.sudo()
        return {
            **data,
            "handler": sudo_self.handler,
            "access_url": sudo_self.access_url,
            "is_user_favorite": sudo_self.is_user_favorite,
            "is_archived": sudo_self.active is False,
            "folder_id": sudo_self.folder_id.id,
            "copy_in_my_drive": self._cannot_create_sibling(),
        }

    @api.constrains("owner_id")
    def _check_owner_is_internal_user(self) -> None:
        spreadsheet_docs = self.filtered(
            lambda rec: rec.handler in ("spreadsheet", "frozen_spreadsheet")
        )
        if any(user.share for user in spreadsheet_docs.owner_id):
            _debug.logic(
                "spreadsheet_owner_refused", reason="portal", documents=spreadsheet_docs
            )
            raise AccessError(
                self.env._("Portal users cannot be the owner of a spreadsheet.")
            )

    def _check_spreadsheet_share(self, operation, access_token) -> None:
        if (
            not self.env.su
            and operation == "write"
            and self.sudo().handler == "frozen_spreadsheet"
        ):
            _debug.logic(
                "spreadsheet_share_denied", records=self, reason="frozen_write"
            )
            raise AccessError(self.env._("You can not edit a frozen spreadsheet"))

        with contextlib.suppress(AccessError):
            super()._check_spreadsheet_share(operation, access_token)
            _debug.logic(
                "spreadsheet_share_granted",
                records=self,
                operation=operation,
                via="record_rules",
            )
            return

        link_token = (access_token or "").rpartition("o")[0]
        try:
            self.env["access.link"]._resolve(
                link_token,
                model=self._name,
                res_id=self.id,
                role="edit" if operation == "write" else "view",
                # a collaborative session calls this on every revision: its
                # use is the page that opened it
                action=None,
            )
            reason = None
        except LinkRefused, LinkLoginRequired:
            reason = "link_refused"
        if (
            reason is None
            and operation == "write"
            and self.sudo().access_via_link != "edit"
        ):
            # the document's own link setting is what its editors chose, as
            # the upload route reads it: a link row saying more opens no edit
            reason = "link_setting_view"
        _debug.logic(
            "spreadsheet_share_denied" if reason else "spreadsheet_share_granted",
            records=self,
            operation=operation,
            via="token",
            reason=reason,
        )
        if reason:
            raise AccessError(self.env._("You don't have access to this document"))

    def _compute_file_extension(self) -> None:
        """Spreadsheet documents do not have file extension."""
        spreadsheet_docs = self.filtered(
            lambda rec: rec.handler in ("spreadsheet", "frozen_spreadsheet")
        )
        spreadsheet_docs.file_extension = False
        super(DocumentsDocument, self - spreadsheet_docs)._compute_file_extension()

    @api.depends("attachment_id", "handler")
    def _compute_spreadsheet_data(self) -> None:
        for document in self.with_context(bin_size=False):
            if document.handler in ("spreadsheet", "frozen_spreadsheet"):
                document.spreadsheet_data = document.attachment_id.raw
            else:
                document.spreadsheet_data = False

    @api.depends("datas", "handler")
    def _compute_spreadsheet_binary_data(self) -> None:
        for document in self:
            if document.handler in ("spreadsheet", "frozen_spreadsheet"):
                document.spreadsheet_binary_data = document.datas
            else:
                document.spreadsheet_binary_data = False

    def _inverse_spreadsheet_binary_data(self) -> None:
        for document in self:
            if document.handler in ("spreadsheet", "frozen_spreadsheet"):
                document.write(
                    {
                        "datas": document.spreadsheet_binary_data,
                        "mimetype": "application/o-spreadsheet",
                    }
                )

    @api.depends_context("uid")
    @api.depends("display_thumbnail")
    def _compute_spreadsheet_thumbnail_checksum(self) -> None:
        spreadsheets = self.filtered(lambda doc: doc.handler == "spreadsheet")
        thumbnails = (
            self.env["ir.attachment"]
            .sudo()
            .search(
                [
                    ("res_model", "=", self._name),
                    ("res_field", "=", "display_thumbnail"),
                    ("res_id", "in", spreadsheets.ids),
                    ("create_uid", "=", self.env.uid),
                ]
            )
        )
        thumbnails_by_documents = thumbnails.grouped("res_id")
        for document in self:
            thumbnail = thumbnails_by_documents.get(document.id)
            if thumbnail:
                document.spreadsheet_thumbnail_checksum = thumbnail.checksum
            else:
                document.spreadsheet_thumbnail_checksum = False

    @api.depends("handler")
    def _compute_thumbnail_source_checksum(self) -> None:
        super()._compute_thumbnail_source_checksum()

    def _get_thumbnail_kind(self) -> str | bool:
        # a spreadsheet's thumbnail is drawn by the spreadsheet, never from
        # its data, and saved along with it
        if self.handler in ("spreadsheet", "frozen_spreadsheet"):
            return "authored"
        return super()._get_thumbnail_kind()

    def _copy_spreadsheet_image_attachments(self) -> None:
        spreadsheets = self.filtered(
            lambda d: d.handler in ("spreadsheet", "frozen_spreadsheet")
        )
        super(DocumentsDocument, spreadsheets)._copy_spreadsheet_image_attachments()

    def _copy_attachment_filter(self, default):
        return (
            super()
            ._copy_attachment_filter(default)
            .filtered(lambda d: d.handler not in ("spreadsheet", "frozen_spreadsheet"))
        )

    def _resize_thumbnail_value(self, vals):
        if "display_thumbnail" in vals:
            return dict(
                vals,
                display_thumbnail=base64.b64encode(
                    image_process(
                        base64.b64decode(vals["display_thumbnail"] or ""),
                        size=(150, 150),
                        crop="center",
                    )
                ),
            )
        return vals

    def _resize_spreadsheet_thumbnails(self, vals_list) -> list:
        return [
            (
                self._resize_thumbnail_value(vals)
                if vals.get("handler") in ("spreadsheet", "frozen_spreadsheet")
                else vals
            )
            for vals in vals_list
        ]

    def _update_spreadsheet_contributors(self) -> None:
        """Add the current user to the spreadsheet contributors."""
        can_write = self.env["spreadsheet.contributor"].has_access("write")
        can_create = self.env["spreadsheet.contributor"].has_access("create")
        if not can_write or not can_create:
            _debug.logic(
                "spreadsheet_contributors_skipped",
                records=self,
                reason="no_contributor_access",
            )
            return
        # Reading ``handler`` to classify the document is internal bookkeeping,
        # not an access decision: the creator of a company-root document may have
        # no read access to it (user_permission 'none'), which would otherwise
        # raise here during create().
        for document in self.sudo():
            if document.handler == "spreadsheet":
                self.env["spreadsheet.contributor"]._update(self.env.user, document)

    @api.model
    def action_view_new_spreadsheet(self, vals=None):
        if vals is None:
            vals = {}
        spreadsheet = self.create(
            {
                "name": self.env._("Untitled spreadsheet"),
                "mimetype": "application/o-spreadsheet",
                "datas": self._empty_spreadsheet_data_base64(),
                "handler": "spreadsheet",
                **vals,
            }
        )
        _debug.lifecycle("spreadsheet_created_blank", document=spreadsheet)
        action_open = spreadsheet.action_view_spreadsheet()
        action_open["params"]["is_new_spreadsheet"] = True
        return action_open

    @api.model
    def _get_spreadsheets_to_display(self, domain, offset=0, limit=None):
        """Get all the spreadsheets, with the spreadsheet the user opened most recently first."""
        # TODO: improve with _read_group to not fetch all records
        Contrib = self.env["spreadsheet.contributor"]
        visible_docs = self.search(
            Domain.AND(
                [domain, [("handler", "in", ("spreadsheet", "frozen_spreadsheet"))]]
            )
        )
        contribs = Contrib.search(
            [
                ("document_id", "in", visible_docs.ids),
                ("user_id", "=", self.env.user.id),
            ],
            order="last_update_date DESC, id DESC",
        )
        user_docs = contribs.document_id
        # Intersection is used to apply the `domain` to `user_doc`, the union is
        # here to keep only the visible docs, but with the order of contribs.
        docs = (user_docs & visible_docs) | visible_docs
        _debug.pipeline(
            "spreadsheets_to_display_ranked",
            visible=len(visible_docs),
            contributed=len(user_docs),
            offset=offset,
            limit=limit,
        )
        if limit:
            docs = docs[offset : offset + limit]
        else:
            docs = docs[offset:]
        return docs.read(["display_name", "display_thumbnail"])

    @api.model
    def _get_fields_shortcuts_copy(self):
        return super()._get_fields_shortcuts_copy() | {"handler"}

    def _clone_xlsx_into_spreadsheet(self, archive_source=False):
        """Clone an XLSX document into a new document with its content unzipped, and return the new document id"""

        unzipped, attachments = self._unzip_xlsx()

        def adjust_role(partner, role):
            """Ensure non-internal users do not have 'edit' access."""
            user_ids = partner.with_context(active_test=False).user_ids
            return "view" if not user_ids or all(user_ids.mapped("share")) else role

        access_ids = [
            Command.create(
                {
                    "partner_id": acc.partner_id.id,
                    "group_id": acc.group_id.id,
                    "company_id": acc.company_id.id,
                    "role": adjust_role(acc.partner_id, acc.role)
                    if acc.partner_id
                    else acc.role,
                }
            )
            for acc in self.access_ids
        ]

        doc = self.copy(
            {
                "access_ids": access_ids,
                "attachment_id": False,
                "handler": "spreadsheet",
                "mimetype": "application/o-spreadsheet",
                "name": self.name.removesuffix(".xlsx"),
                "spreadsheet_data": json_dumps(unzipped),
            }
        )

        for attachment in attachments:
            attachment.write({"res_id": doc.id})

        _debug.pipeline(
            "spreadsheet_xlsx_imported",
            source=self,
            spreadsheet=doc,
            parts=len(unzipped),
            images=len(attachments),
            accesses=len(access_ids),
        )
        return doc.id

    def _clone_csv_into_spreadsheet(self):
        csv_data = self._read_csv()
        spreadsheet_data = self._convert_csv_to_spreadsheet_data(csv_data)

        doc = self.copy(
            {
                "attachment_id": False,
                "handler": "spreadsheet",
                "mimetype": "application/o-spreadsheet",
                "name": self.name.removesuffix(".csv"),
                "spreadsheet_data": json_dumps(spreadsheet_data),
            }
        )

        _debug.pipeline(
            "spreadsheet_csv_imported",
            source=self,
            spreadsheet=doc,
            rows=len(csv_data),
            cells=len(spreadsheet_data["sheets"][0]["cells"]),
        )
        return doc.id

    def import_to_spreadsheet(self, archive_source=False):
        self.check_singleton()
        with _debug.perf(
            "spreadsheet_import",
            cr=self.env.cr,
            records=self,
            mimetype=self.mimetype,
            archive_source=archive_source,
        ):
            if self.mimetype == "text/csv":
                document_id = self._clone_csv_into_spreadsheet()
            else:
                document_id = self._clone_xlsx_into_spreadsheet()
        if archive_source:
            self.action_archive()
        return document_id

    def _read_csv(self):
        base_import_record = self.env["base_import.import"].create(
            {
                "file": self.attachment_id.raw,
                "file_type": "text/csv",
            }
        )
        return base_import_record._read_csv({"encoding": "utf-8", "quoting": '"'})

    def _convert_csv_to_spreadsheet_data(self, csv_data):
        def get_column_name(n):
            """Helper function to get the spreadsheet column
            name in letters (A -> Z) from the column index.
            Example: 1 -> A, 2 -> B, 27 -> AA, 28 -> AB, etc.
            """
            res = []
            while n > 0:
                n, remainder = divmod(n - 1, 26)
                res.append(chr(65 + remainder))
            return "".join(res[::-1])

        data = {"sheets": [{"cells": {}}]}

        for row_index, row in enumerate(csv_data):
            for col_index, cell_content in enumerate(row):
                if cell_content:
                    col_name = get_column_name(col_index + 1)
                    cell_ref = f"{col_name}{row_index + 1}"
                    data["sheets"][0]["cells"][cell_ref] = cell_content
        return data

    def _get_is_multipage(self):
        """Override for spreadsheets and xlsx."""
        is_multipage = super()._get_is_multipage()
        if is_multipage is not None:
            return is_multipage

        if self.mimetype in XLSX_MIME_TYPES and self.attachment_id.raw:
            file = io.BytesIO(self.attachment_id.raw)
            if not zipfile.is_zipfile(file):
                return None
            with zipfile.ZipFile(file) as archive:
                if "[Content_Types].xml" not in archive.namelist():
                    # the xlsx file is invalid
                    _debug.logic(
                        "spreadsheet_multipage_unknown",
                        records=self,
                        reason="xlsx_without_content_types",
                    )
                    return None
                with archive.open("[Content_Types].xml") as myfile:
                    content = myfile.read()
                    tree = etree.fromstring(content)
                    nodes = tree.xpath(
                        "//ns:Override[@ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml']",
                        namespaces={
                            "ns": "http://schemas.openxmlformats.org/package/2006/content-types"
                        },
                    )
                    return len(nodes) > 1

        if self.handler in ("spreadsheet", "frozen_spreadsheet"):
            spreadsheet_data = json_loads(self.spreadsheet_data or "{}")
            if spreadsheet_data.get("sheets"):
                return len(spreadsheet_data["sheets"]) > 1
            return self._is_xlsx_data_multipage(spreadsheet_data)
        return None

    @api.model
    def _is_xlsx_data_multipage(self, spreadsheet_data) -> bool:
        for filename, content in spreadsheet_data.items():
            if filename.endswith("workbook.xml.rels"):
                tree = etree.fromstring(content.encode())
                nodes = tree.findall(
                    ".//rels:Relationship",
                    {
                        "rels": "http://schemas.openxmlformats.org/package/2006/relationships"
                    },
                )
                found_first_sheet = False
                for node in nodes:
                    if node.attrib["Type"].endswith("/relationships/worksheet"):
                        if found_first_sheet:
                            return True
                        found_first_sheet = True
                break

        return False

    def _unzip_xlsx(self) -> tuple:
        file = io.BytesIO(self.attachment_id.raw)
        if not zipfile.is_zipfile(file) or self.mimetype not in XLSX_MIME_TYPES:
            _debug.logic(
                "spreadsheet_xlsx_rejected",
                records=self,
                reason="not_xlsx",
                mimetype=self.mimetype,
            )
            raise UserError(self.env._("The file is not a xlsx file"))

        unzipped_size = 0
        with zipfile.ZipFile(file) as input_zip:
            if len(input_zip.infolist()) > 1000:
                _debug.logic(
                    "spreadsheet_xlsx_rejected",
                    records=self,
                    reason="too_many_entries",
                    entries=len(input_zip.infolist()),
                )
                raise UserError(self.env._("The xlsx file is too big"))

            if "[Content_Types].xml" not in input_zip.namelist() or not any(
                name.startswith("xl/") for name in input_zip.namelist()
            ):
                _debug.logic(
                    "spreadsheet_xlsx_rejected", records=self, reason="corrupted"
                )
                raise UserError(self.env._("The xlsx file is corrupted"))

            unzipped = {}
            attachments = []
            for info in input_zip.infolist():
                if not (
                    info.filename.endswith((".xml", ".xml.rels"))
                    or "media/image" in info.filename
                ) or not info.filename.startswith(SUPPORTED_PATHS):
                    # Don't extract files others than xmls or unsupported xmls
                    continue

                unzipped_size += info.file_size
                if unzipped_size > 50 * 1000 * 1000:  # 50MB
                    _debug.logic(
                        "spreadsheet_xlsx_rejected",
                        records=self,
                        reason="uncompressed_too_big",
                        bytes=unzipped_size,
                    )
                    raise UserError(self.env._("The xlsx file is too big"))

                if info.filename.endswith((".xml", ".xml.rels")):
                    unzipped[info.filename] = input_zip.read(info.filename).decode()
                elif "media/image" in info.filename:
                    image_file = input_zip.read(info.filename)
                    attachment = self._upload_image_file(image_file, info.filename)
                    attachments.append(attachment)
                    unzipped[info.filename] = {
                        "imageSrc": "/web/image/" + str(attachment.id),
                    }
        _debug.pipeline(
            "spreadsheet_xlsx_unzipped",
            records=self,
            parts=len(unzipped),
            images=len(attachments),
            bytes=unzipped_size,
        )
        return unzipped, attachments

    def _upload_image_file(self, image_file, filename):
        attachment_model = self.env["ir.attachment"]
        attachment = attachment_model.create(
            {
                "name": filename,
                "datas": base64.encodebytes(image_file),
                "res_model": "document.document",
            }
        )
        attachment._post_add_create()
        return attachment

    def action_view_spreadsheet(self):
        self.check_singleton()
        return {
            "type": "ir.actions.client",
            "tag": "action_view_spreadsheet",
            "params": {
                "spreadsheet_id": self.id,
            },
        }

    @api.readonly
    @api.model
    def get_spreadsheets(self, domain=(), offset=0, limit=None) -> dict:
        domain = Domain.AND([domain, [("handler", "=", "spreadsheet")]])
        return {
            "records": self._get_spreadsheets_to_display(domain, offset, limit),
            "total": self.search_count(domain),
        }

    @api.model
    def _get_spreadsheet_selector(self) -> dict | None:
        return {
            "model": self._name,
            "display_name": self.env._("Spreadsheets"),
            "sequence": 0,
            "allow_create": True,
        }

    def _contains_live_data(self):
        """Return true if the spreadsheet contains live data, like Odoo pivots, chart, etc."""
        self.check_singleton()
        if self.handler != "spreadsheet":
            return False

        snapshot = json_loads(self._get_spreadsheet_serialized_snapshot())
        if (
            snapshot.get("lists")
            or snapshot.get("pivots")
            or snapshot.get("chartOdooMenusReferences")
        ):
            _debug.logic(
                "spreadsheet_live_data_detected", records=self, source="snapshot_data"
            )
            return True

        for sheet in snapshot.get("sheets", []):
            for figure in sheet.get("figures", []):
                if figure.get("data", {}).get("type", "").startswith("odoo_"):
                    _debug.logic(
                        "spreadsheet_live_data_detected",
                        records=self,
                        source="snapshot_chart",
                    )
                    return True

        has_live_revision = any(
            command.get("type")
            in ("INSERT_ODOO_LIST", "ADD_PIVOT", "LINK_ODOO_MENU_TO_CHART")
            or (
                command.get("type") == "CREATE_CHART"
                and command.get("definition", {}).get("type", "").startswith("odoo_")
            )
            for revision in self.spreadsheet_revision_ids
            for command in json_loads(revision.commands).get("commands", [])
        )
        _debug.logic(
            "spreadsheet_live_data_detected"
            if has_live_revision
            else "spreadsheet_live_data_absent",
            records=self,
            source="revisions",
        )
        return has_live_revision

    def _get_writable_record_name_field(self):
        return "name"

    @api.model
    def create_xlsx_attachment_from_spreadsheet(self, spreadsheet_files) -> list[dict]:
        """Creates XLSX attachments from spreadsheet JSON exports

        :param spreadsheet_files: list of dicts with 'name', 'files', 'res_model' and 'res_id'

        :return: list of media info dicts
        :rtype: list[dict]
        """
        attachments = []

        _debug.pipeline(
            "spreadsheet_xlsx_attachments_requested",
            spreadsheets=len(spreadsheet_files),
        )
        for sheet in spreadsheet_files:
            content = self.env["mixin.spreadsheet"]._zip_xslx_files(sheet["files"])
            attachment = self.env["ir.attachment"].create(
                {
                    "name": sheet["name"],
                    "datas": base64.b64encode(content).decode(),
                    "res_model": sheet["res_model"],
                    "res_id": sheet["res_id"],
                    "type": "binary",
                    "mimetype": mimetype_for("xlsx"),
                }
            )
            attachments.append(attachment)
        return [a._get_media_info() for a in attachments]
