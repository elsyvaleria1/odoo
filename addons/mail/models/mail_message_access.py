import logging
from collections import defaultdict
from collections.abc import Collection

from odoo import api, models
from odoo.api import DomainType
from odoo.exceptions import AccessError, MissingError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, Query
from odoo.tools.access_scan import prepare_document_access_error
from odoo.tools.owner_reach import owner_reach, search_by_owner

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class MailMessage(models.Model):
    _inherit = "mail.message"
    _search_visibility_fields = (
        "model",
        "res_id",
        "author_id",
        "create_uid",
        "message_type",
        "partner_ids",
        "is_internal",
        "subtype_id",
    )

    @api.model
    def _search(
        self,
        domain: DomainType,
        offset: int = 0,
        limit: int | None = None,
        order: str | None = None,
        *,
        bypass_access: bool = False,
        **kwargs,
    ) -> Query:
        if self.env.is_superuser() or bypass_access:
            return super()._search(
                domain, offset, limit, order, bypass_access=True, **kwargs
            )

        domain = Domain(domain)
        if not self.env.user._is_internal():
            domain &= self._get_search_domain_non_internal()
        _debug.logic(
            "search_by",
            by="owner_reach",
            internal=self.env.user._is_internal(),
            limit=limit,
        )
        return search_by_owner(
            self,
            domain,
            offset,
            limit,
            order,
            super()._search,
            lambda only, bounded: self._get_search_reach_domain(
                bounded=bounded, only=only
            ),
            "model",
            **kwargs,
        )

    @api.model
    def _get_search_reach_domain(
        self, *, bounded: bool = False, only: Collection[str] | None = None
    ) -> Domain:
        pid = self.env.user.partner_id.id
        direct = Domain("partner_ids", "in", [pid]) | Domain(
            "notification_ids.res_partner_id", "=", pid
        )
        if (author_pid := self._get_author_partner_id_for_access()) is not None:
            direct |= Domain("author_id", "=", author_pid)
        if (creator_uid := self._get_creator_uid_for_access()) is not None:
            direct |= Domain("create_uid", "=", creator_uid)
        on_documents = Domain("message_type", "!=", "user_notification") & owner_reach(
            self,
            "model",
            "res_id",
            lambda Document: Document._mail_message_read_reach(),
            probe=bounded,
            only=only,
        )
        return direct | on_documents

    def _get_search_domain_non_internal(self) -> Domain:
        return Domain("message_type", "!=", "comment") | self._get_search_domain_share()

    def _get_search_domain_share(self) -> Domain:
        return (
            Domain("is_internal", "=", False)
            & Domain("subtype_id", "!=", False)
            & Domain("subtype_id.internal", "=", False)
        )

    def _get_accessible_documents(
        self, doc_model: str, doc_res_ids: Collection[int], operation: str
    ) -> models.Model:
        documents_all = (
            self.env[doc_model].with_context(active_test=False).browse(doc_res_ids)
        )
        operation_res_ids = (
            documents_all._mail_group_by_operation_for_mail_message_operation(operation)
        )

        allowed_ids = []
        for record_operation, records in operation_res_ids.items():
            forbidden_doc_ids = set()
            try:
                operation_result = records._check_access(record_operation)
            except MissingError:
                existing = records.exists()
                forbidden_doc_ids = set((records - existing).ids)
                operation_result = existing._check_access(record_operation)
            if operation_result:
                forbidden_doc_ids |= set(operation_result[0]._ids)
            allowed_ids += [
                record.id for record in records if record.id not in forbidden_doc_ids
            ]

        _debug.perf.count(
            "documents_checked",
            model=doc_model,
            operation=operation,
            asked=len(documents_all),
            operations=sorted(operation_res_ids),
            allowed=len(allowed_ids),
        )
        return self.env[doc_model].browse(allowed_ids)

    @api.model
    def _get_ids_on_readable_documents(self, model_ids: dict[str, dict]) -> set:
        allowed_ids = set()
        for doc_model, doc_dict in model_ids.items():
            if doc_model not in self.env or not self.env[doc_model].has_access("read"):
                _debug.logic(
                    "model_unreadable", model=doc_model, documents=len(doc_dict)
                )
                continue
            allowed = self._get_accessible_documents(doc_model, list(doc_dict), "read")
            allowed_ids |= {
                msg_id
                for document_id in allowed.ids
                for msg_id in doc_dict[document_id]
            }
        return allowed_ids

    def _check_access(self, operation: str) -> tuple | None:
        result = super()._check_access(operation)
        if not self:
            return result

        messages = self - result[0] if result else self
        if messages and (forbidden := messages._get_forbidden_access(operation)):
            denied = (result[0] + forbidden) if result else forbidden
            result = (denied, lambda: denied._prepare_access_error(operation))
        return result

    def _get_forbidden_access(self, operation: str) -> api.Self:
        forbidden = self.browse()

        if not self.env.user._is_internal():
            internal = self._get_forbidden_internal(operation)
            forbidden += internal
            self -= internal
            if not self:
                return forbidden

        remaining = self._get_access_values(operation)
        asked = len(remaining)
        self._discard_own_messages(remaining, operation)
        own = asked - len(remaining)
        if operation == "read":
            self._discard_notified_messages(remaining)
        documents = self._group_ids_by_document(remaining)
        before_documents = len(remaining)
        self._discard_accessible_documents(remaining, documents, operation)
        by_document = before_documents - len(remaining)
        if operation == "create":
            self._discard_notified_parents(remaining)
            self._discard_followed_documents(remaining, documents)

        _debug.logic(
            "access_scanned",
            operation=operation,
            asked=asked,
            internal_forbidden=len(forbidden),
            own=own,
            notified=asked - own - before_documents,
            documents=sum(len(docs) for docs in documents.values()),
            by_document=by_document,
            by_parent_or_follow=before_documents - by_document - len(remaining),
            forbidden=len(remaining),
        )
        return forbidden + self.browse(remaining)

    def _get_forbidden_internal(self, operation: str) -> api.Self:
        messages = self.sudo()
        messages.fetch(["is_internal", "subtype_id", "message_type"])
        messages.subtype_id.fetch(["internal"])
        comments_only = operation in ("create", "read")
        return self.browse(
            message.id
            for message in messages
            if (not comments_only or message.message_type == "comment")
            and (
                message.is_internal
                or not message.subtype_id
                or message.subtype_id.internal
            )
        )

    def _get_access_values(self, operation: str) -> dict:
        if operation in ("write", "create", "unlink"):
            messages = self.sudo()
            messages.fetch(
                ["model", "res_id", "author_id", "parent_id", "message_type"]
            )
            return {
                message.id: {
                    "id": message.id,
                    "model": message.model,
                    "res_id": message.res_id,
                    "author_id": message.author_id.id,
                    "parent_id": message.parent_id.id,
                    "message_type": message.message_type,
                }
                for message in messages
            }
        if operation != "read":
            raise ValueError(f"Wrong operation name ({operation})")
        self.flush_recordset(
            [
                "model",
                "res_id",
                "author_id",
                "create_uid",
                "parent_id",
                "message_type",
                "partner_ids",
            ]
        )
        self.env["mail.notification"].flush_model(["mail_message_id", "res_partner_id"])
        query = SQL(
            """ SELECT m.id, m.model, m.res_id, m.author_id, m.create_uid, m.parent_id,
                    bool_or(partner_rel.res_partner_id IS NOT NULL OR needaction_rel.res_partner_id IS NOT NULL) AS notified,
                    m.message_type
                FROM "mail_message" m
                LEFT JOIN "mail_message_res_partner_rel" partner_rel
                    ON partner_rel.mail_message_id = m.id AND partner_rel.res_partner_id = %(pid)s
                LEFT JOIN "mail_notification" needaction_rel
                    ON needaction_rel.mail_message_id = m.id AND needaction_rel.res_partner_id = %(pid)s
                WHERE m.id = ANY(%(ids)s)
                GROUP BY m.id
            """,
            pid=self.env.user.partner_id.id,
            ids=self.ids,
        )
        return {values["id"]: values for values in self.env.execute_query_dict(query)}

    def _get_creator_uid_for_access(self) -> int | None:
        return None if self.env.user._is_public() else self.env.uid

    def _get_author_partner_id_for_access(self) -> int | None:
        return None if self.env.user._is_public() else self.env.user.partner_id.id

    def _discard_own_messages(self, remaining: dict, operation: str) -> None:
        author_pid = self._get_author_partner_id_for_access()
        creator_uid = self._get_creator_uid_for_access()
        for mid, message in list(remaining.items()):
            if operation == "read":
                accessible = (
                    author_pid is not None and message.get("author_id") == author_pid
                ) or (
                    creator_uid is not None and message.get("create_uid") == creator_uid
                )
            elif operation == "write":
                accessible = (
                    author_pid is not None and message.get("author_id") == author_pid
                )
            elif operation == "create":
                accessible = not self._is_thread_message_visible(vals=message)
            else:
                accessible = False
            if accessible:
                remaining.pop(mid, None)

    def _discard_notified_messages(self, remaining: dict) -> None:
        for mid, message in list(remaining.items()):
            if message.get("notified"):
                remaining.pop(mid, None)

    def _group_ids_by_document(self, remaining: dict) -> dict:
        documents = defaultdict(lambda: defaultdict(list))
        for mid, message in remaining.items():
            if (
                message.get("model")
                and message.get("res_id")
                and message.get("message_type") != "user_notification"
                and message["model"] in self.env
            ):
                documents[message["model"]][message["res_id"]].append(mid)
        return documents

    def _discard_accessible_documents(
        self, remaining: dict, documents: dict, operation: str
    ) -> None:
        if not remaining:
            return
        for model, docid_msgids in documents.items():
            allowed_ids = set(
                self._get_accessible_documents(
                    model, list(docid_msgids), operation
                )._ids
            )
            for doc_id, msg_ids in docid_msgids.items():
                if doc_id in allowed_ids:
                    for mid in msg_ids:
                        remaining.pop(mid, None)

    def _discard_notified_parents(self, remaining: dict) -> None:
        if not remaining:
            return
        parent_ids_msg_ids = defaultdict(list)
        for mid, message in remaining.items():
            if message.get("parent_id"):
                parent_ids_msg_ids[message["parent_id"]].append(mid)
        if not parent_ids_msg_ids:
            return
        query = SQL(
            """ SELECT m.id, m.model, m.res_id
                FROM "mail_message" m
                JOIN "mail_message_res_partner_rel" partner_rel
                    ON partner_rel.mail_message_id = m.id AND partner_rel.res_partner_id = %s
                WHERE m.id = ANY(%s) """,
            self.env.user.partner_id.id,
            list(parent_ids_msg_ids),
        )
        for parent_id, parent_model, parent_res_id in self.env.execute_query(query):
            for mid in parent_ids_msg_ids[parent_id]:
                child = remaining.get(mid)
                if (
                    child
                    and child.get("model") == parent_model
                    and child.get("res_id") == parent_res_id
                ):
                    remaining.pop(mid, None)

    @api.model
    def _get_followed_res_ids(
        self, doc_model: str, doc_res_ids: Collection[int]
    ) -> set[int]:
        if not doc_res_ids:
            return set()
        return set(
            self.env["mail.followers"]
            .sudo()
            .search_fetch(
                [
                    ("res_model", "=", doc_model),
                    ("res_id", "in", list(doc_res_ids)),
                    ("partner_id", "=", self.env.user.partner_id.id),
                ],
                ["res_id"],
            )
            .mapped("res_id")
        )

    def _discard_followed_documents(self, remaining: dict, documents: dict) -> None:
        if not remaining:
            return
        for model, docid_msgids in documents.items():
            for res_id in self._get_followed_res_ids(model, docid_msgids):
                for mid in docid_msgids[res_id]:
                    remaining.pop(mid, None)

    def _prepare_access_error(self, operation: str) -> AccessError:
        return prepare_document_access_error(self, operation)
