from collections import defaultdict

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL

_debug = DebugLog(__name__)


class DocumentsDocument(models.Model):
    _inherit = "document.document"

    def _action_update_members(
        self, partners: dict, no_propagation: bool = False
    ) -> tuple:
        self.env["document.access"].flush_model()
        created_or_updated_access = []
        removed_access = []
        for partner, (role, date_to) in partners.items():
            for change in self._set_principal_access(
                ("partner", partner.id, False), role, date_to
            ):
                if change[0] == "removed":
                    removed_access.append(change[1:3])
                else:
                    created_or_updated_access.append(change)
        _debug.pipeline(
            "members_updated",
            documents=self,
            partners=len(partners),
            changed=len(created_or_updated_access),
            removed=len(removed_access),
        )
        self._invalidate_permission_cache(["access_ids"])
        return created_or_updated_access, removed_access

    @api.model
    def _add_user_role_without_propagation(
        self, role: str, documents_per_user: dict
    ) -> None:
        existing_access = (
            self.env["document.access"]
            .sudo()
            .search(
                Domain("cause_ref", "=", False)
                & Domain.OR(
                    [
                        ("partner_id", "=", owner.partner_id.id),
                        ("document_id", "in", documents.ids),
                    ]
                    for owner, documents in documents_per_user.items()
                )
            )
        )
        _debug.lifecycle(
            "owner_role_kept",
            role=role,
            users=len(documents_per_user),
            existing=len(existing_access),
        )
        roles = self._access_graph.roles
        existing_access.filtered(
            lambda access: roles.index(access.role) < roles.index(role)
        ).role = role
        existing_access_values = {
            (a.partner_id, a.document_id) for a in existing_access
        }
        self.env["document.access"].sudo().create(
            [
                {
                    "partner_id": owner.partner_id.id,
                    "document_id": document.id,
                    "role": role,
                }
                for owner, documents in documents_per_user.items()
                for document in documents
                if (owner.partner_id, document) not in existing_access_values
            ]
        )

    def _propagation_target_select(
        self, extra: Domain = Domain.TRUE, *, no_propagation: bool = False, access: bool
    ) -> SQL:
        domain = Domain.AND(
            (
                extra,
                Domain("shortcut_document_id", "=", False),
                Domain("id", "in" if no_propagation else "child_of", self.ids),
                self._get_domain_access_update()
                if access
                else self._get_domain_propagation(),
            )
        )
        return self.with_context(active_test=False)._search(domain).select()

    def _get_domain_propagation(self) -> Domain:
        return Domain.TRUE if self.env.su else Domain("user_permission", "=", "edit")

    def _get_domain_access_update(self) -> Domain:
        return self._get_domain_propagation()

    @api.model
    def _shortcuts_union_sql(
        self, source: str, columns: tuple[str, ...] = ("id",), *, include: bool = True
    ) -> SQL:
        projection = SQL(", ").join(SQL.identifier(column) for column in columns)
        base = SQL("SELECT %s FROM %s", projection, SQL.identifier(source))
        if not include:
            return base
        return SQL(
            """%s
                     UNION
                    SELECT %s
                      FROM document_document AS shortcut
                      JOIN %s AS shortcut_target
                        ON shortcut_target.id = shortcut.shortcut_document_id""",
            base,
            SQL(", ").join(SQL.identifier("shortcut", column) for column in columns),
            SQL.identifier(source),
        )

    @api.model
    def _update_changes_by_document_dict(
        self,
        created_or_updated_access: list,
        removed_access: list,
        changes_by_document_dict: dict,
    ) -> None:
        old_values = defaultdict(dict)
        for action, doc, partner, role, exp in created_or_updated_access:
            exp = fields.Date.to_string(exp) or "None"
            partner_dict = changes_by_document_dict.setdefault(doc, {}).setdefault(
                "members", {"added": {}, "updated": {}, "removed": []}
            )
            if action == "upsert":
                if old := old_values[doc].get(partner):
                    partner_dict["updated"][partner] = {
                        "role": (old["role"], role),
                        "date_to": (old["date_to"], exp),
                    }
                else:
                    partner_dict["added"][partner] = {
                        "role": role,
                        "date_to": exp,
                    }
            elif action == "existing":
                old_values[doc][partner] = {
                    "role": role,
                    "date_to": exp,
                }
        for doc, partner in removed_access:
            (
                changes_by_document_dict.setdefault(doc, {})
                .setdefault("members", {"added": {}, "updated": {}, "removed": []})[
                    "removed"
                ]
                .append(partner)
            )

    def _update_company(self, company_id: int | bool) -> None:
        self.flush_model()
        to_update = self._propagation_target_select(
            Domain("id", "in", self.ids) | Domain("company_id", "!=", company_id),
            access=False,
        )
        self.env.cr.execute(
            SQL(
                """
                    WITH documents_to_update AS (%(to_update)s),
                    documents_and_shortcuts AS (%(documents_and_shortcuts)s)
                    UPDATE document_document
                       SET %(field)s = %(value)s
                      FROM documents_and_shortcuts AS doc
                     WHERE document_document.id = doc.id
                """,
                field=SQL("company_id"),
                value=company_id or None,
                to_update=to_update,
                documents_and_shortcuts=self._shortcuts_union_sql(
                    "documents_to_update", include=bool(company_id)
                ),
            )
        )
        _debug.pipeline(
            "company_propagated",
            documents=self,
            company=company_id,
            rows=self.env.cr.rowcount,
        )

        self._invalidate_permission_cache(["company_id"])
