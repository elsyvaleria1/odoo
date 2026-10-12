from collections.abc import Hashable
from typing import TYPE_CHECKING, Any

from markupsafe import Markup

from odoo import Command, models
from odoo.exceptions import UserError
from odoo.tools.misc import clean_context

if TYPE_CHECKING:
    from .approval_request_line import ApprovalRequestLine


class ApprovalRequest(models.Model):
    _inherit = "approval.request"

    def _get_target_model(self) -> str:
        return self.target_model or ""

    def _get_target_line_field(self) -> str:
        return ""

    def _get_target_line_parent_field(self) -> str:
        return ""

    def _get_target_document_line_field(self) -> str:
        return "line_ids"

    def _get_target_line_quantity_field(self) -> str:
        return "product_qty"

    def _get_target_line_backref_field(self) -> str:
        return "approval_request_line_id"

    def _get_target_document_name(self) -> str:
        model = self._get_target_model()
        return self.env["ir.model"]._get(model).name if model else ""

    def _get_target_document_label(self) -> str:
        return self._get_target_document_name()

    def _get_target_log_label(self) -> str:
        return self._get_target_document_name()

    def _get_target_log_prefix(self) -> str:
        return ""

    def _is_target_configured(self) -> bool:
        return bool(
            self._get_target_model()
            and self._get_target_line_field()
            and self._get_target_line_parent_field(),
        )

    def _get_target_line_comodel(self) -> str:
        link_field = self._get_target_line_field()
        if not link_field:
            return ""
        return self.env["approval.request.line"]._fields[link_field].comodel_name

    def _get_documents_of_model(
        self, model: str, link_field: str, parent_field: str
    ) -> models.BaseModel:
        self.check_singleton()
        documents_from_lines = self.sudo().line_ids[link_field][parent_field]
        if self._origin.id:
            documents_from_mixin = (
                self.env[model]
                .sudo()
                .search([("approval_request_id", "=", self._origin.id)])
            )
        else:
            documents_from_mixin = self.env[model]
        return documents_from_lines | documents_from_mixin

    def _documents_of_model_by_request(
        self, model: str, link_field: str, parent_field: str
    ) -> dict[int, models.BaseModel]:
        empty = self.env[model]
        persisted = self.filtered(lambda request: request._origin.id)
        from_mixin: dict[int, Any] = {}
        if persisted:
            found = (
                self.env[model]
                .sudo()
                .search([("approval_request_id", "in", persisted._origin.ids)])
            )
            for document in found:
                key = document.approval_request_id.id
                from_mixin[key] = from_mixin.get(key, empty) | document
        return {
            request.id: (
                request.line_ids[link_field][parent_field]
                | from_mixin.get(request._origin.id, empty)
            )
            for request in self.sudo()
        }

    def _check_withdraw_blocked_by(
        self, documents: models.BaseModel, label: str
    ) -> None:
        sources = {(request.res_model, request.res_id) for request in self.sudo()}
        active = documents.filtered(
            lambda document: (
                document.state != "cancel"
                and (document._name, document.id) not in sources
            )
        )
        self._raise_withdraw_blocked(active, label)

    def _get_target_documents(self) -> models.BaseModel:
        self.check_singleton()
        if not self._is_target_configured():
            model = self._get_target_model()
            return self.env[model] if model else self.env["approval.request"].browse()
        return self._get_documents_of_model(
            self._get_target_model(),
            self._get_target_line_field(),
            self._get_target_line_parent_field(),
        )

    def _get_target_pending_lines(self) -> ApprovalRequestLine:
        link_field = self._get_target_line_field()
        if not link_field:
            return self.line_ids.browse()
        return self.line_ids.filtered(lambda line: not line[link_field])

    def action_view_target_documents(self) -> dict[str, Any]:
        self.check_singleton()
        documents = self._get_target_documents()
        return {
            "name": self._get_target_document_name(),
            "type": "ir.actions.act_window",
            "res_model": self._get_target_model(),
            "view_mode": "list,form",
            "context": clean_context(self.env.context),
            "domain": [("id", "in", documents.ids)],
        }

    def action_create_target_documents(self) -> dict[str, Any]:
        self.check_singleton()
        self._check_target_creation_allowed()
        self._create_target_documents()
        self._log_target_creation_to_chatter()
        return self.action_view_target_documents()

    def _check_target_creation_allowed(self) -> None:
        self.check_singleton()
        if self.state != "approved":
            raise UserError(
                self.env._(
                    "%(documents)s can only be created from an APPROVED request. "
                    "Request '%(name)s' is in state '%(state)s'.",
                    documents=self._get_target_document_name(),
                    name=self.display_name,
                    state=self.state,
                ),
            )

    def _check_target_prerequisites(self, lines: ApprovalRequestLine) -> None:
        return None

    def _get_target_group_key(self, line: ApprovalRequestLine) -> Hashable:
        return line.partner_id.id or self.partner_id.id or False

    def _prepare_target_document_values(
        self, key: Any, lines: ApprovalRequestLine
    ) -> dict[str, Any]:
        raise NotImplementedError

    def _prepare_target_line_values(
        self,
        line: ApprovalRequestLine,
        key: Any,
        document: models.BaseModel,
        lines: ApprovalRequestLine,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def _post_create_target_document(
        self, document: models.BaseModel, key: Any, lines: ApprovalRequestLine
    ) -> None:
        return None

    def _is_target_line_creatable(self, line: ApprovalRequestLine) -> bool:
        return True

    def _get_target_document_context(self) -> dict[str, Any]:
        return {}

    def _create_target_documents(self) -> models.BaseModel:
        self.check_singleton()
        if not self.line_ids:
            raise UserError(
                self.env._(
                    "Cannot create %(documents)s from an empty approval request.",
                    documents=self._get_target_document_name().lower(),
                ),
            )

        lines_to_process = self._get_target_pending_lines()
        if not lines_to_process:
            if self._is_target_recreation_silent():
                return self.env[self._get_target_model()]
            raise UserError(
                self.env._(
                    "All lines of this request already have %(documents)s lines "
                    "— nothing left to create.",
                    documents=self._get_target_document_label().lower(),
                ),
            )

        self._check_target_prerequisites(lines_to_process)

        lines_by_key: dict[Hashable, ApprovalRequestLine] = {}
        for line in lines_to_process:
            key = self._get_target_group_key(line)
            lines_by_key.setdefault(key, self.env["approval.request.line"])
            lines_by_key[key] |= line

        documents = self.env[self._get_target_model()]
        for key, lines in lines_by_key.items():
            documents |= self._create_target_document(key, lines)
        return documents

    def _create_target_document(
        self, key: Any, lines: ApprovalRequestLine
    ) -> models.BaseModel:
        document_values = self._prepare_target_document_values(key, lines)
        document = (
            self.env[self._get_target_model()]
            .with_context(**self._get_target_document_context())
            .create(document_values)
        )

        creatable_lines = lines.filtered(self._is_target_line_creatable)
        backref_field = self._get_target_line_backref_field()
        document.write(
            {
                self._get_target_document_line_field(): [
                    Command.create(
                        {
                            **self._prepare_target_line_values(
                                line,
                                key,
                                document,
                                lines,
                            ),
                            backref_field: line.id,
                        }
                    )
                    for line in creatable_lines
                ],
            },
        )

        self._link_produced_documents(document)
        self._update_target_line_links(document, lines)
        self._post_create_target_document(document, key, lines)
        return document

    def _update_target_line_links(
        self, document: models.BaseModel, lines: ApprovalRequestLine
    ) -> None:
        link_field = self._get_target_line_field()
        document_lines = document[self._get_target_document_line_field()]

        backref_field = self._get_target_line_backref_field()
        for line in lines:
            if not self._is_target_line_creatable(line):
                continue
            matching = document_lines.filtered(
                lambda document_line, source=line: (
                    document_line[backref_field].id == source.id
                ),
            )
            if len(matching) == 1:
                line.sudo()[link_field] = matching.id
            elif len(matching) > 1:
                raise UserError(
                    self.env._(
                        "Data integrity error: multiple %(documents)s lines found "
                        "for approval line %(line_id)s (product: %(product)s). "
                        "Please contact your administrator.",
                        documents=self._get_target_document_label().lower(),
                        line_id=line.id,
                        product=line.product_id.display_name,
                    ),
                )
            else:
                raise UserError(
                    self.env._(
                        "Failed to link the %(documents)s line for approval line "
                        "%(line_id)s (product: %(product)s). The line was not "
                        "created properly. Please contact your administrator.",
                        documents=self._get_target_document_label().lower(),
                        line_id=line.id,
                        product=line.product_id.display_name,
                    ),
                )

    def _is_target_rollback_enabled(self) -> bool:
        return False

    def _is_target_recreation_silent(self) -> bool:
        return False

    def _get_target_document_removable_lines(
        self, document: models.BaseModel
    ) -> models.BaseModel:
        return document[self._get_target_document_line_field()]

    def _remove_target_document(self, document: models.BaseModel) -> None:
        document.write({"state": "cancel"})
        document.unlink()

    def _is_target_document_removable(self, document: models.BaseModel) -> bool:
        return document.state == "draft"

    def _refuse_approval_request(self) -> None:
        super()._refuse_approval_request()
        if not (self._is_target_configured() and self._is_target_rollback_enabled()):
            return

        link_field = self._get_target_line_field()
        parent_field = self._get_target_line_parent_field()
        quantity_field = self._get_target_line_quantity_field()

        sudo_self = self.sudo()
        documents = sudo_self.line_ids[link_field][parent_field]
        refusal_data: dict[str, list[dict[str, Any]]] = {
            "removed": [],
            "require_manual_action": [],
        }

        for document in documents:
            source_lines = sudo_self.line_ids.filtered(
                lambda line, target=document: (
                    line[link_field][parent_field].id == target.id
                ),
            )

            if self._is_target_document_removable(document):
                refusal_data["removed"].extend(
                    self._get_target_document_data(source_lines),
                )

                removed_lines = self.env[self._get_target_line_comodel()].sudo()
                for source_line in source_lines:
                    document_line = source_line[link_field]
                    remaining = document_line[quantity_field] - source_line.quantity
                    if remaining > 0:
                        document_line[quantity_field] = remaining
                    else:
                        removed_lines |= document_line

                if len(self._get_target_document_removable_lines(document)) == len(
                    removed_lines,
                ):
                    self._remove_target_document(document)
                elif removed_lines:
                    removed_lines.unlink()
            else:
                refusal_data["require_manual_action"].extend(
                    self._get_target_document_data(
                        source_lines,
                        include_raw_data=True,
                    ),
                )

            source_lines.sudo()[link_field] = False

        if refusal_data["removed"] or refusal_data["require_manual_action"]:
            self._log_target_refusal_to_chatter(refusal_data)

    def _get_target_document_data(
        self, source_lines: ApprovalRequestLine, include_raw_data: bool = False
    ) -> list[dict[str, Any]]:
        link_field = self._get_target_line_field()
        parent_field = self._get_target_line_parent_field()

        documents_data = []
        grouped = source_lines.grouped(
            lambda line: line[link_field][parent_field],
        )
        for document, lines in grouped.items():
            document_data = {}
            if include_raw_data:
                document_data["document"] = document
                document_data["source_lines"] = lines
            document_data["document_name"] = document.name
            document_data["products"] = [
                (line.product_id.name, line.quantity) for line in lines
            ]
            documents_data.append(document_data)
        return documents_data

    def _get_target_log_headers(self) -> dict[str, str]:
        label = self._get_target_log_label()
        return {
            "created": self.env._(
                "The following products have been added to the %(documents)s:",
                documents=label,
            ),
            "removed": self.env._(
                "The following products have been removed from the %(documents)s:",
                documents=label,
            ),
            "require_manual_action": self.env._(
                "The following products couldn't be removed because the "
                "%(documents)s are not in draft state:",
                documents=label,
            ),
        }

    def _prepare_target_log_message(
        self, document_state: str, documents_data: list[dict[str, Any]]
    ) -> Markup:
        return Markup("%(log_msg_header)s<br> <br> %(document_log)s <hr>") % {
            "log_msg_header": self._get_target_log_headers().get(document_state, ""),
            "document_log": Markup().join(
                Markup("%(prefix)s%(document_name)s: <br> <ul>%(product_lines)s</ul>")
                % {
                    "prefix": self._get_target_log_prefix(),
                    "document_name": document_data["document_name"],
                    "product_lines": Markup().join(
                        Markup("<li>%(quantity)s %(name)s</li>")
                        % {"name": product[0], "quantity": product[1]}
                        for product in document_data["products"]
                    ),
                }
                for document_data in documents_data
            ),
        }

    def _log_target_creation_to_chatter(self) -> None:
        documents_data = self._get_target_document_data(self.line_ids)
        self._message_log(
            body=self._prepare_target_log_message("created", documents_data),
        )

    def _log_target_refusal_to_chatter(
        self, refusal_data: dict[str, list[dict[str, Any]]]
    ) -> None:
        refusal_log = Markup()
        for document_state in ("removed", "require_manual_action"):
            documents_data = refusal_data[document_state]
            if documents_data:
                refusal_log += self._prepare_target_log_message(
                    document_state,
                    documents_data,
                )
            if document_state == "require_manual_action":
                self._log_target_refusal_to_document_chatter(documents_data)
        self._message_log(body=refusal_log)

    def _log_target_refusal_to_document_chatter(
        self, documents_data: list[dict[str, Any]]
    ) -> None:
        for document_data in documents_data:
            document = document_data["document"]
            source_lines = document_data["source_lines"]

            product_list = Markup().join(
                Markup("<li>%(quantity)s x %(product)s</li>")
                % {
                    "quantity": line.quantity,
                    "product": line.product_id.display_name,
                }
                for line in source_lines
            )

            document.message_post(
                body=Markup(
                    self.env._(
                        "<p><strong>Warning: Approval Request Refused</strong></p>"
                        "<p>Approval request %(request)s was refused, but this "
                        "%(document)s is already confirmed. The following products "
                        "from the approval could not be automatically removed:</p>"
                        "<ul>%(products)s</ul>"
                        "<p>Please review this %(document)s and update manually if "
                        "needed.</p>"
                    )
                )
                % {
                    "request": self.name,
                    "document": self._get_target_document_label().lower(),
                    "products": product_list,
                },
                subject=self.env._("Approval Request Refused"),
                message_type="notification",
                subtype_xmlid="mail.mt_note",
            )
