import typing
from collections import defaultdict
from typing import Any

from odoo import Command, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL

from odoo.addons.document.tools import UserFolder, is_mimetype_inline_rendered

_debug = DebugLog(__name__)

_PERMISSION_READERS = frozenset({"user_folder_id", "user_can_move"})


class DocumentsDocument(models.Model):
    _inherit = "document.document"

    @api.model
    def _user_is_documents_manager(self) -> bool:
        return self.env.user.has_group("document.group_documents_manager")

    def _is_documents_manager(self) -> bool:
        return self.env.su or self._user_is_documents_manager()

    @api.model
    def _raise_company_folder_manager_only(self) -> None:
        raise AccessError(
            self.env._("Only Documents Managers can create in company folder.")
        )

    def _check_access_or_raise(self, operation: str, message: str) -> None:
        try:
            self.check_access(operation)
        except UserError as error:
            raise AccessError(message) from error

    @api.depends_context("uid", "allowed_company_ids")
    @api.depends(
        "access_ids",
        "access_ids.role",
        "access_ids.date_to",
        "access_ids.partner_id",
        "access_ids.group_id",
        "access_scope_path",
        "is_access_restricted",
        "access_via_link",
        "owner_id",
        "is_access_via_link_hidden",
        "company_id",
        "folder_id",
        "shortcut_document_id",
        "shortcut_document_owner_id",
    )
    def _compute_user_permission(self) -> None:
        self.user_permission = "none"

        saved = self.filtered(lambda document: isinstance(document.id, int))
        for document in self - saved:
            document.user_permission = (
                document._origin.user_permission if document._origin else "edit"
            )
        if not saved:
            return

        with _debug.perf("user_permission_reach", cr=self.env.cr, documents=len(saved)):
            self._access_graph_flush()
            self.flush_model(self._user_permission_domain_fields())

            documents_sudo = (
                self.env["document.document"].sudo().with_context(active_test=False)
            )
            in_scope = Domain("id", "in", saved.ids)
            reachable = documents_sudo._search(
                in_scope & self._search_user_permission("in", ["view", "edit"])
            )
            editable = documents_sudo._search(
                in_scope & self._search_user_permission("in", ["edit"])
            )
            self.env.cr.execute(
                SQL(
                    """SELECT reachable.id, reachable.id IN (%(editable)s)
                         FROM (%(reachable)s) AS reachable""",
                    editable=editable.select(),
                    reachable=reachable.select(),
                )
            )
            levels = {
                document_id: "edit" if is_editable else "view"
                for document_id, is_editable in self.env.cr.fetchall()
            }
        _debug.perf.count(
            "user_permission_computed", documents=saved, resolved=len(levels)
        )
        for document in saved:
            document.user_permission = levels.get(document.id, "none")

    @api.depends(
        "active",
        "lock_uid",
        "user_permission",
        "folder_id.user_permission",
        "owner_id",
        "user_folder_id",
    )
    @api.depends_context("uid", "allowed_company_ids")
    def _compute_user_can_move(self) -> None:
        if self.env.su:
            for document in self:
                document.user_can_move = document.active
            return
        active_documents = self.filtered("active") - self._locked_by_other()
        (self - active_documents).user_can_move = False
        if self.env.user.has_group("document.group_documents_system"):
            movable = active_documents.filtered(lambda d: d.user_permission == "edit")
            _debug.logic("user_can_move", by="system_group", documents=movable)
            movable.user_can_move = True
            (active_documents - movable).user_can_move = False
            return
        owned_documents = active_documents.filtered(
            lambda doc: doc.owner_id == self.env.user
        )
        owned_documents.user_can_move = True
        if unowned_documents := active_documents - owned_documents:
            is_manager = self._user_is_documents_manager()
            for document in unowned_documents:
                document.user_can_move = (
                    document.user_permission == "edit"
                    and (
                        not document.folder_id
                        or document.folder_id.user_permission == "edit"
                    )
                    and (is_manager or document.user_folder_id != UserFolder.COMPANY)
                )

    @api.depends("lock_uid")
    @api.depends_context("uid")
    def _compute_is_locked_by_other(self) -> None:
        locked = self._locked_by_other()
        locked.is_locked_by_other = True
        (self - locked).is_locked_by_other = False

    @api.model
    def _search_is_locked_by_other(self, operator: str, value: typing.Any) -> Domain:
        if operator != "in":
            return NotImplemented
        if self.env.su or self._is_documents_manager():
            locked = Domain.FALSE
        else:
            locked = Domain("lock_uid", "!=", False) & Domain(
                "lock_uid", "!=", self.env.uid
            )
        if set(value) == {True}:
            return locked
        if set(value) == {False}:
            return ~locked
        return NotImplemented

    @api.depends(
        "active",
        "type",
        "lock_uid",
        "owner_id",
        "user_permission",
        "folder_id.user_permission",
    )
    @api.depends_context("uid", "allowed_company_ids")
    def _compute_user_can_trash(self) -> None:
        if self.env.su:
            self.user_can_trash = True
            return
        candidates = self.browse()
        if not self.env.user.share:
            candidates = (
                self.filtered(
                    lambda d: (
                        d.active
                        and d.user_permission == "edit"
                        and (
                            d.owner_id == self.env.user
                            or not d.folder_id
                            or d.folder_id.user_permission == "edit"
                        )
                    )
                )
                - self._locked_by_other()
            )
        candidates -= candidates._folders_used_by_companies()
        candidates.user_can_trash = True
        (self - candidates).user_can_trash = False

    def _check_access_label_change(self) -> None:
        if self.env.su or not self:
            return
        self.invalidate_recordset(["user_can_manage"])
        if not all(self.mapped("user_can_manage")):
            raise AccessError(
                self.env._("Only who manages a document changes its sensitivity label.")
            )

    @api.depends_context("uid", "allowed_company_ids")
    @api.depends("user_permission", "access_role")
    def _compute_user_can_manage(self) -> None:
        saved = self.filtered(lambda document: isinstance(document.id, int))
        (self - saved).user_can_manage = True
        if not saved:
            return
        managed = set(
            self.with_context(active_test=False)
            ._search(Domain("id", "in", saved.ids) & self._search_user_can_manage())
            .get_result_ids()
        )
        for document in saved:
            document.user_can_manage = document.id in managed

    def _search_user_can_manage(
        self, operator: str = "in", value: typing.Any = (True,)
    ) -> Domain:
        if operator not in ("in", "not in"):
            return NotImplemented
        user = self.env.user
        if user._is_public() or user.share:
            domain = Domain.FALSE
        elif self.sudo(False)._is_documents_manager():
            domain = self._search_user_permission("in", ["edit"])
        else:
            domain = self._graph_reach("manage")
        domain &= self._access_label_reach("manage")
        wants = True in value
        if operator == "not in":
            wants = not wants
        return domain if wants else ~domain

    @api.model
    def _documents_system_reach(self) -> Domain:
        if self.env.user._is_superuser():
            return Domain.TRUE
        policy = self.env.registry.access_policy
        permissions, guards = policy.bound_access_rows(
            self.env, self._name, "system_reach"
        )
        if not permissions:
            return Domain.FALSE
        if policy.bound_access_rows(self.env, self._name, "open_drives")[0]:
            return Domain.TRUE
        return Domain.OR(permissions) & Domain.AND(guards)

    def _access_predicate_outside_others_drives(
        self, bind: typing.Any, args: dict
    ) -> Domain:
        user_id = bind("user")

        def to_sql(model: typing.Any, alias: str, query: typing.Any) -> SQL:
            model.flush_model(["parent_path", "folder_id", "owner_id"])
            return SQL(
                """split_part(%s, '/', 1)::int NOT IN (
                       SELECT id FROM document_document
                        WHERE folder_id IS NULL
                          AND owner_id IS NOT NULL
                          AND owner_id != %s)""",
                SQL.identifier(alias, "parent_path"),
                user_id,
            )

        return Domain.custom(to_sql=to_sql)

    def _search_user_permission(
        self,
        operator: str,
        value: list | str,
        exclude_ownership: bool = False,
        *,
        ignore_link: bool = False,
    ) -> Domain:
        if self.env.user._is_public():
            return Domain.FALSE
        searched_roles = {"view", "edit", "none"}
        if operator == "in":
            searched_roles.intersection_update(value)
        elif operator == "not in":
            searched_roles.difference_update(value)
        else:
            return NotImplemented

        searched_roles.discard("none")
        if not searched_roles:
            return Domain.FALSE

        system = self._documents_system_reach()
        everything = system & Domain.OR(
            [
                Domain("company_id", "in", self.env.companies.ids),
                Domain("company_id", "not in", self.env.user.company_ids.ids),
                Domain("company_id.active", "=", False),
            ]
        )
        if system.is_true() and not self.env.user.company_ids - self.env.companies:
            editable = reachable = everything
        else:
            folded = (
                not system.is_false()
                and not system.is_true()
                and not self.env.user.share
                and self._folds_system_reach()
            )
            editable = self._reach(
                "edit", ignore_link, exclude_ownership=exclude_ownership, system=folded
            )
            if self.env.user.share:
                editable &= ~self._kept_from_share_editors()
            reachable = self._reach(
                "view", ignore_link, exclude_ownership=exclude_ownership, system=folded
            )
            if not folded:
                editable |= everything
                reachable |= everything
        edit_label = self._access_label_reach("edit")
        if searched_roles == {"edit"}:
            return editable & edit_label
        viewable = reachable & self._access_label_reach("view")
        if searched_roles == {"view"}:
            return viewable & ~(editable & edit_label)
        return viewable

    @api.model
    def _kept_from_share_editors(self) -> Domain:
        return Domain.FALSE

    @api.model
    def _user_permission_domain_fields(self) -> list:
        return [
            "access_scope_path",
            "access_via_link",
            "active",
            "company_id",
            "folder_id",
            "is_access_restricted",
            "is_access_via_link_hidden",
            "owner_id",
            "shortcut_document_id",
            "shortcut_document_owner_id",
            "type",
        ]

    @api.model
    def _internal_audience_group(self) -> int:
        return self.env.ref("base.group_user").id

    def _graph_reach(self, role: str, *, exclude_ownership: bool = False) -> Domain:
        exclude = [self._internal_audience_group()] if role == "manage" else []
        return self._access_graph_domain(
            role, exclude_groups=exclude, owner=not exclude_ownership
        )

    def _reach(
        self,
        role: str,
        ignore_link: bool,
        *,
        exclude_ownership: bool = False,
        system: bool = False,
    ) -> Domain:
        return self._permission_reach(
            role,
            links=not (exclude_ownership or ignore_link),
            exclude_ownership=exclude_ownership,
            system=system,
        )

    @api.depends(
        "access_ids.role",
        "access_ids.group_id",
        "access_ids.date_to",
        "access_scope_path",
        "shortcut_document_id.access_internal",
    )
    def _compute_access_internal(self) -> None:
        targets = self.shortcut_document_id
        nodes = (self - self.filtered("shortcut_document_id")) | targets
        ranks = nodes._access_graph_group_ranks(self._internal_audience_group())
        levels = (None, "view", "edit", "edit")
        for document in self:
            node = document.shortcut_document_id or document
            rank = ranks.get(node.id) if isinstance(node.id, int) else None
            document.access_internal = levels[rank] if rank else "none"

    def _inverse_access_internal(self) -> None:
        for level, documents in self.grouped("access_internal").items():
            documents._set_internal_access(level or "none")

    def _search_access_internal(self, operator: str, value: typing.Any) -> Domain:
        if operator not in ("in", "not in"):
            return NotImplemented
        asked = set(value)
        if operator == "not in":
            asked = {"none", "view", "edit"} - asked
        reach = {
            role: self._access_graph_domain(
                role,
                groups=[self._internal_audience_group()],
                partner=False,
                owner=False,
            )
            for role in ("view", "edit")
        }
        bands = {
            "none": ~reach["view"],
            "view": reach["view"] & ~reach["edit"],
            "edit": reach["edit"],
        }
        return Domain.OR(bands[level] for level in asked if level in bands)

    def _read_format(
        self, fnames: typing.Sequence[str], load: str | None = "_classic_read"
    ) -> list:
        self._check_content_read(fnames)
        if _PERMISSION_READERS & set(fnames):
            (self | self.folder_id).mapped("user_permission")
        return super()._read_format(fnames, load=load)

    def export_data(self, fields_to_export: list[str]) -> dict[str, list]:
        self._check_content_read([path.split("/")[0] for path in fields_to_export])
        return super().export_data(fields_to_export)

    def _check_content_read(self, fnames: typing.Iterable[str]) -> None:
        if self.env.su or not {"raw", "datas"} & set(fnames):
            return
        Binary = self.env["ir.binary"]
        for document in self:
            Binary._check_document_content_served(document.attachment_id)

    def _is_download_allowed(self) -> bool:
        self.check_singleton()
        target = self.shortcut_document_id or self
        allowed = not target.is_download_blocked or (
            target.user_permission == "edit" or target.access_via_link == "edit"
        )
        if _debug.logic.enabled:
            _debug.logic(
                "download_gate",
                document=self,
                target=target,
                allowed=allowed,
                blocked=target.is_download_blocked,
                permission=target.user_permission,
                via_link=target.access_via_link,
            )
        return allowed

    def _is_inline_content_allowed(self) -> bool:
        self.check_singleton()
        if self._is_download_allowed():
            return True
        target = self.shortcut_document_id or self
        renderable = is_mimetype_inline_rendered(target.mimetype)
        _debug.logic(
            "inline_gate",
            document=self,
            target=target,
            allowed=renderable,
            mimetype=target.mimetype or "",
        )
        return renderable

    def action_update_access_rights(
        self,
        access_internal: str | None = None,
        access_via_link: str | None = None,
        is_access_via_link_hidden: bool | None = None,
        partners: dict | None = None,
        no_propagation: bool = False,
        is_download_blocked: bool | None = None,
        is_access_restricted: bool | None = None,
    ) -> list | None:
        if len(self.ids) == 0:
            return None
        self._raise_if_locked_by_other("access_update")
        self._check_access_update_allowed(
            (
                access_internal,
                access_via_link,
                is_access_via_link_hidden,
                is_access_restricted,
            ),
            is_download_blocked,
            partners,
        )
        return self._update_access_rights(
            access_internal,
            access_via_link,
            is_access_via_link_hidden,
            partners=partners,
            no_propagation=no_propagation,
            is_download_blocked=is_download_blocked,
            is_access_restricted=is_access_restricted,
        )

    def _check_access_update_allowed(
        self,
        settings: tuple,
        is_download_blocked: bool | None,
        partners: dict | None,
    ) -> None:
        if self.env.su:
            return
        user = self.env.user
        if user.share and (
            partners
            or is_download_blocked is not None
            or any(value is not None for value in settings)
        ):
            _debug.logic("access_update_refused", reason="share_user", documents=self)
            raise AccessError(
                self.env._("Only internal users can change who can access documents.")
            )
        own_change = next(
            (
                change
                for partner, change in (partners or {}).items()
                if (
                    partner.id
                    if isinstance(partner, models.BaseModel)
                    else int(partner)
                )
                == user.partner_id.id
            ),
            None,
        )
        leaving = own_change is not None and own_change[0] is False
        changes_anything = (
            len(partners or {}) > (1 if leaving else 0)
            or is_download_blocked is not None
            or any(value is not None for value in settings)
        )
        if changes_anything and not self._may_manage_access():
            _debug.logic("access_update_refused", reason="not_manager", documents=self)
            raise AccessError(
                self.env._(
                    "Only whoever manages a document (its owner, someone it is "
                    "shared with as manager, or a Documents manager) can change "
                    "who can access it."
                )
            )
        if (
            own_change is not None
            and own_change[0] is not False
            and any(document.owner_id != user for document in self)
            and not self._is_documents_manager()
        ):
            _debug.logic(
                "access_update_refused", reason="own_membership", documents=self
            )
            raise AccessError(
                self.env._(
                    "You cannot change your own access to documents you do not own."
                )
            )

    def _update_access_rights(
        self,
        access_internal: str | None = None,
        access_via_link: str | None = None,
        is_access_via_link_hidden: bool | None = None,
        partners: dict | None = None,
        no_propagation: bool = False,
        is_download_blocked: bool | None = None,
        is_access_restricted: bool | None = None,
    ) -> list | None:
        if len(self.ids) == 0:
            return None
        self._check_access_or_raise(
            "write", self.env._("You are not allowed to update these access rights.")
        )

        if self.shortcut_document_id:
            _debug.logic("access_update_refused", reason="shortcut", documents=self)
            raise UserError(
                self.env._(
                    "You can not update the access of a shortcut, update its target instead."
                )
            )

        access_options = {"view", "edit", "none", None}
        hidden_options = {None, True, False}
        role_options = {"manage", "edit", "view", False, None}
        incorrect_fields_to_options = {
            **(
                {"is_access_via_link_hidden": hidden_options}
                if is_access_via_link_hidden not in hidden_options
                else {}
            ),
            **(
                {"is_download_blocked": hidden_options}
                if is_download_blocked not in hidden_options
                else {}
            ),
            **(
                {"is_access_restricted": hidden_options}
                if is_access_restricted not in hidden_options
                else {}
            ),
            **(
                {"access_via_link": access_options}
                if access_via_link not in access_options
                else {}
            ),
            **(
                {"access_internal": access_options}
                if access_internal not in access_options
                else {}
            ),
            **(
                {"partners.role": role_options}
                if any(
                    role not in role_options for (role, __) in (partners or {}).values()
                )
                else {}
            ),
        }
        if incorrect_fields_to_options:
            _debug.logic(
                "access_update_refused",
                reason="bad_values",
                fields=sorted(incorrect_fields_to_options),
            )
            hints = "\n- " + "\n- ".join(
                f"{name}: {options}"
                for name, options in incorrect_fields_to_options.items()
            )
            raise UserError(
                self.env._(
                    "Incorrect values. Use one of the following for the following fields: %(hints)s.)",
                    hints=hints,
                )
            )

        if is_access_restricted is not None and (
            changed := self.filtered(
                lambda d: (
                    not d.shortcut_document_id
                    and d.is_access_restricted != is_access_restricted
                )
            )
        ):
            changed.is_access_restricted = is_access_restricted
            self._invalidate_permission_cache(["is_access_restricted"])

        member_changes = None
        if partners:
            partners = {
                self.env["res.partner"].browse(int(partner))
                if isinstance(partner, str | int)
                else partner: (
                    role,
                    fields.Datetime.to_datetime(exp)
                    if exp and isinstance(exp, str)
                    else exp,
                )
                for partner, (role, exp) in (partners or {}).items()
            }
            _debug.pipeline(
                "access_members_update",
                documents=self,
                partners=len(partners),
                propagate=not no_propagation,
            )
            member_changes = self._action_update_members(
                partners, no_propagation=no_propagation
            )

        changes_by_document_dict = self._action_update_access(
            access_internal,
            access_via_link,
            is_access_via_link_hidden,
            no_propagation=no_propagation,
            is_download_blocked=is_download_blocked,
        )
        if member_changes:
            created_or_updated_access, removed_access = member_changes
            self._update_changes_by_document_dict(
                created_or_updated_access, removed_access, changes_by_document_dict
            )

        self.env["document.access.tracking"]._create_access_tracking(
            changes_by_document_dict
        )
        _debug.lifecycle(
            "access_rights_updated",
            documents=self,
            changed=len(changes_by_document_dict),
        )

        return self.mapped("user_permission")

    def _action_update_access(
        self,
        access_internal: str | None,
        access_via_link: str | None,
        is_access_via_link_hidden: bool | None,
        no_propagation: bool = False,
        is_download_blocked: bool | None = None,
    ) -> dict:
        self.flush_model()
        changes_by_document_dict = defaultdict(dict)
        if access_internal is not None:
            documents = self.filtered(lambda d: not d.shortcut_document_id)
            before = {document.id: document.access_internal for document in documents}
            documents._set_internal_access(access_internal)
            documents.invalidate_recordset(["access_internal"])
            for document in documents:
                if document.access_internal != before[document.id]:
                    changes_by_document_dict[document.id]["access_internal"] = before[
                        document.id
                    ]
        for field, value in (
            ("access_via_link", access_via_link),
            ("is_access_via_link_hidden", is_access_via_link_hidden),
            ("is_download_blocked", is_download_blocked),
        ):
            if value is None:
                continue

            skip_propagation = no_propagation or field == "is_access_via_link_hidden"
            _debug.pipeline("access_field_update", field=field, skip=skip_propagation)

            candidates_domain = Domain(
                [
                    ("shortcut_document_id", "=", False),
                    ("id", "in" if skip_propagation else "child_of", self.ids),
                ]
            )
            candidates_domain &= self._get_domain_access_update()
            candidates_query = self.with_context(active_test=False)._search(
                candidates_domain
            )

            candidates = candidates_query.select(
                *(
                    self._field_to_sql(candidates_query.table, fname, candidates_query)
                    for fname in ("id", "folder_id", "shortcut_document_id", field)
                )
            )

            self.env.cr.execute(
                SQL(
                    """
                WITH RECURSIVE candidates AS (%(candidates)s),
                -- explore the folders
                documents_to_update AS (
                    SELECT id, %(field)s
                      FROM candidates
                     WHERE id = ANY(%(root_ids)s)
                     UNION
                    SELECT child.id, child.%(field)s
                      FROM candidates AS child
                      JOIN documents_to_update AS parent
                        ON child.folder_id = parent.id
                ),
                -- document.shortcut_ids are updated in "SUDO" to stay in sync
                documents_and_shortcuts AS (%(documents_and_shortcuts)s)
                    UPDATE document_document
                       SET %(field)s = %(value)s
                      FROM documents_and_shortcuts AS doc
                        -- document | document.children_ids | document.shortcut_ids
                     WHERE document_document.id = doc.id
                       -- only rows that actually change: no needless write, and
                       -- tracking is returned the old value of a real change
                       AND document_document.%(field)s IS DISTINCT FROM %(value)s
                 RETURNING doc.id, doc.%(field)s
            """,
                    field=SQL.identifier(field),
                    value=value,
                    root_ids=self.ids,
                    candidates=candidates,
                    documents_and_shortcuts=self._shortcuts_union_sql(
                        "documents_to_update", ("id", field)
                    ),
                )
            )

            for id, old_value in self.env.cr.fetchall():
                changes_by_document_dict[id][field] = old_value
            _debug.perf.count("access_field_rows", field=field, value=value)

        self._invalidate_permission_cache(
            ["access_via_link", "is_access_via_link_hidden", "is_download_blocked"]
        )
        if link_changed := [
            document_id
            for document_id, changes in changes_by_document_dict.items()
            if "access_via_link" in changes
        ]:
            self.browse(link_changed).with_privilege(
                "base.privilege_manage_links",
                reason="a folder's link setting reached its subtree",
            )._sync_document_links(roles=dict.fromkeys(link_changed, access_via_link))

        return changes_by_document_dict

    @api.model
    def _invalidate_permission_cache(self, fields_written: list[str]) -> None:
        permissions = [
            self._fields[name]
            for name in (
                "user_permission",
                "access_role",
                "access_internal",
                "user_can_manage",
            )
        ]
        dependents = {
            field.name
            for permission in permissions
            for field in self.pool.get_dependent_fields(permission)
            if field.model_name == self._name and not field.store
        }
        _debug.pipeline(
            "permission_cache_invalidated",
            written=fields_written,
            dependents=len(dependents),
        )
        self.invalidate_model(
            [*fields_written, *(field.name for field in permissions), *dependents]
        )

    @api.model
    def _holds_privilege(self, name: str) -> bool:
        privilege = self.env.registry.access_policy.privilege_ids(self.env, (name,))
        return bool(privilege & self.env.privileges)

    def _may_manage_access(self) -> bool:
        if self.env.su or self._holds_privilege("document.privilege_share_documents"):
            return True
        return all(self.mapped("user_can_manage"))

    @api.model
    def _source_ranks(self, sources: list[dict], key_of: Any) -> dict:
        roles = self._access_graph.roles
        ranks: dict = {}
        for source in sources:
            if (key := key_of(source)) is not None:
                ranks[key] = max(ranks.get(key, 0), roles.index(source["role"]) + 1)
        return ranks

    def _member_roles(self) -> dict:
        self.check_singleton()
        roles = self._access_graph.roles
        ranks = self._source_ranks(
            (self.shortcut_document_id or self)._access_graph_sources(),
            lambda source: source["partner"] or None,
        )
        return {partner: roles[rank - 1] for partner, rank in ranks.items()}

    @api.model
    def _grant_key(self, partner: Any, group: Any, company: Any) -> tuple:
        if partner:
            return ("partner", partner.id, False)
        return ("group", group.id, company.id or False)

    def _inherited_ranks(self) -> dict[tuple, int]:
        self.check_singleton()
        return self._source_ranks(
            self._access_graph_sources(),
            lambda source: (
                self._grant_key(source["partner"], source["group"], source["company"])
                if source["inherited"]
                else None
            ),
        )

    def _own_grants(self) -> dict[tuple, Any]:
        self.check_singleton()
        return {
            self._grant_key(
                access.partner_id, access.group_id, access.company_id
            ): access
            for access in self.access_ids
        }

    def _update_access_boundary(self, excluded: set[tuple]) -> None:
        self._keep_as_own(self._inherited_ranks(), excluded)
        self._sharing().is_access_restricted = True
        _debug.lifecycle("access_boundary_made", document=self, excluded=len(excluded))

    def _keep_as_own(self, ranks: dict[tuple, int], excluded: set[tuple]) -> None:
        roles = self._access_graph.roles
        sharing_env = self._sharing().env
        own = {
            key: grant.with_env(sharing_env)
            for key, grant in self._own_grants().items()
        }
        creates = []
        for key, rank in ranks.items():
            if key in excluded:
                continue
            role = roles[min(rank, len(roles)) - 1]
            if row := own.get(key):
                if roles.index(row.role) + 1 < rank:
                    row.role = role
                continue
            kind, principal_id, company_id = key
            creates.append(
                {
                    "document_id": self.id,
                    f"{kind}_id": principal_id,
                    "company_id": company_id,
                    "role": role,
                    "cause": "manual",
                }
            )
        self._sharing().env["document.access"].create(creates)

    def _keep_group_grants_of_folder(self) -> None:
        self.check_singleton()
        ranks = self._source_ranks(
            self.folder_id._access_graph_sources(),
            lambda source: (
                self._grant_key(False, source["group"], source["company"])
                if source["group"]
                else None
            ),
        )
        self._keep_as_own(ranks, set())

    def _set_principal_access(
        self, key: tuple, role: str | bool, date_to: Any = None
    ) -> list[tuple]:
        roles = self._access_graph.roles
        Access = self._sharing().env["document.access"]
        kind, principal_id, company_id = key
        leaving = self._leaving(key)
        changes = []
        for document in self.filtered(lambda d: not d.shortcut_document_id):
            if kind == "partner" and principal_id == document.owner_id.partner_id.id:
                continue
            inherited = document._inherited_ranks().get(key, 0)
            row = document._own_grants().get(key, Access).with_env(Access.env)
            wanted = roles.index(role) + 1 if role else 0
            if role is None:
                if row and date_to is not None:
                    changes.append(
                        ("existing", document.id, principal_id, row.role, row.date_to)
                    )
                    row.date_to = date_to or False
                    changes.append(
                        ("upsert", document.id, principal_id, row.role, row.date_to)
                    )
                continue
            if wanted < inherited and not leaving:
                document._update_access_boundary({key})
                inherited = 0
                row = document._own_grants().get(key, Access).with_env(Access.env)
            if row:
                changes.append(
                    ("existing", document.id, principal_id, row.role, row.date_to)
                )
            if not wanted or (wanted <= inherited and not date_to):
                if row:
                    row.unlink()
                    changes.append(("removed", document.id, principal_id, None, None))
                continue
            values = {"role": role}
            if date_to is not None:
                values["date_to"] = date_to or False
            if row:
                row.write(values)
            else:
                row = Access.create(
                    {
                        "document_id": document.id,
                        f"{kind}_id": principal_id,
                        "company_id": company_id,
                        **values,
                    }
                )
            changes.append(("upsert", document.id, principal_id, row.role, row.date_to))
        return changes

    def _sharing(self) -> DocumentsDocument:
        return self.with_privilege(
            "document.privilege_share_documents",
            reason="whoever manages a document changes who can access it",
        )

    def _leaving(self, key: tuple) -> bool:
        return (
            key == ("partner", self.env.user.partner_id.id, False)
            and not self.env.su
            and not self._may_manage_access()
        )

    def _set_internal_access(self, level: str) -> None:
        self._set_principal_access(
            ("group", self._internal_audience_group(), False),
            False if level == "none" else level,
        )

    def _get_permission_without_token(self) -> str:
        self.check_singleton()
        return self._get_permission_without_token_multi()[self]

    def _get_permission_without_token_multi(self) -> dict:
        permission_by_document = dict.fromkeys(self, "none")
        saved = self.filtered(lambda document: isinstance(document.id, int))
        if not saved:
            return permission_by_document

        self.flush_model(self._user_permission_domain_fields())
        self.env["document.access"].flush_model(
            ["document_id", "partner_id", "role", "date_to"]
        )
        documents_sudo = (
            self.env["document.document"].sudo().with_context(active_test=False)
        )
        in_scope = Domain("id", "in", saved.ids)
        levels = {}
        for level in ("view", "edit"):
            query = documents_sudo._search(
                in_scope & self._search_user_permission("in", [level], ignore_link=True)
            )
            levels.update(dict.fromkeys(query.get_result_ids(), level))
        _debug.perf.count(
            "permission_without_token", documents=saved, resolved=len(levels)
        )
        for document in saved:
            permission_by_document[document] = levels.get(document.id, "none")
        return permission_by_document

    def _get_unauthorized_root_document_owners_sudo(self) -> models.Model:
        return self.mapped("owner_id").sudo().filtered("share")

    @api.model
    def _validated_create_access_commands(self, access_ids: Any) -> list:
        commands = list(access_ids or [])
        for command in commands:
            code = command[0] if isinstance(command, list | tuple) else command
            if code in (Command.CREATE, Command.CLEAR):
                continue
            if code == Command.SET and not command[2]:
                continue
            _debug.logic("access_command_refused", code=code)
            raise UserError(
                self.env._(
                    "Document access can only be granted at creation "
                    "(Command.create) or cleared; got command %s.",
                    code,
                )
            )
        return commands

    def _cannot_create_sibling(self) -> bool:
        self.check_singleton()
        if self.env.su:
            return False
        if self.folder_id:
            return self.folder_id.user_permission != "edit"
        return not self._user_is_documents_manager() and self.owner_id != self.env.user

    def _is_company_root_folder(self) -> bool:
        self.check_singleton()
        return self.type == "folder" and not self.folder_id and not self.owner_id

    @api.model
    def _archive_denied_message(self) -> str:
        return self.env._(
            "You do not have sufficient access rights to delete these documents."
        )

    def _raise_if_unauthorized_archive(self) -> None:
        if self.env.su:
            return
        unowned_documents = self.filtered(
            lambda d: d.active and d.owner_id != self.env.user
        )
        if any(
            folder.user_permission != "edit" for folder in unowned_documents.folder_id
        ):
            _debug.logic(
                "archive_refused",
                reason="unowned_in_uneditable_folder",
                documents=unowned_documents,
            )
            raise UserError(self._archive_denied_message())
