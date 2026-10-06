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

# the fields whose compute reads user_permission of the document's folder too
_PERMISSION_READERS = frozenset({"user_folder_id", "user_can_move"})


class DocumentsDocument(models.Model):
    _inherit = "document.document"

    @api.model
    def _user_is_documents_manager(self) -> bool:
        # the user's membership whatever the env's elevation: what a reach is
        # built on, since reaches are also built under sudo for the real user
        return self.env.user.has_group("document.group_documents_manager")

    def _is_documents_manager(self) -> bool:
        # may this call act as a Documents manager: the membership, or sudo.
        # A Settings administrator outside the Documents groups is not one --
        # the reach never treated them as one, and this check used to
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
        "user_permission",
        "folder_id.user_permission",
        "owner_id",
        "user_folder_id",
    )
    @api.depends_context("uid", "allowed_company_ids")
    def _compute_user_can_move(self) -> None:
        active_documents = self.filtered("active")
        (self - active_documents).user_can_move = False
        if self.env.su:
            active_documents.user_can_move = True
            return
        if self.env.user.has_group("document.group_documents_system"):
            # what the system reach gives them, which stops at another
            # person's drive: the rest the move itself would refuse
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
        # who changes a document's grants, audience, boundary and link: whoever
        # holds manage on it (its owner, an owner above it, a manage grant),
        # and the Documents managers and administrators wherever they edit
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
        # what the Documents system administrators reach whoever shared it:
        # every document outside another person's drive, and inside it too
        # while they hold break-glass (decision I1); nothing for anyone else
        # read from the rows themselves: the verbs' own required operation is
        # decided by user_permission, which this term computes
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
        # a document whose tree is not another person's drive: the top of its
        # parent_path is not a top-level node someone else owns. The whole
        # ancestry, not the access scope, which a boundary cuts short
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
            # every document lies in a company in use, one the user is not in or
            # an archived one: the grants reach nothing more
            editable = reachable = everything
        else:
            editable = self._reach(
                "edit", ignore_link, exclude_ownership=exclude_ownership
            )
            if self.env.user.share:
                # what an external user may only view, whatever reaches them
                editable &= ~self._kept_from_share_editors()
            reachable = self._reach(
                "view", ignore_link, exclude_ownership=exclude_ownership
            )
            editable |= everything
            reachable |= everything
        edit_label = self._access_label_reach("edit")
        if searched_roles == {"edit"}:
            return editable & edit_label
        viewable = reachable & self._access_label_reach("view")
        if searched_roles == {"view"}:
            return viewable & ~(editable & edit_label)
        # what reaches for edit reaches for view, and no label lets writing
        # without reading (ir.access.class.can_label): the edit band adds nothing
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

    def _permission_company_domain(self) -> Domain:
        # a document of a company in use, of none, or of one the user is not
        # in: the company switcher, which the access graph holds for what it
        # reaches, and a document found through its folder's link needs too
        every_company_ids = self.env.user.with_context(
            active_test=False
        ).company_ids.ids
        return Domain("company_id", "in", self.env.companies.ids) | Domain(
            "company_id", "not in", every_company_ids
        )

    @api.model
    def _internal_audience_group(self) -> int:
        return self.env.ref("base.group_user").id

    def _graph_reach(self, role: str, *, exclude_ownership: bool = False) -> Domain:
        # what the grants reach, live down the folders: the access graph, which
        # keeps to the companies in use, the internal audience (base.group_user)
        # being one of the user's groups. Nobody manages through the audience
        exclude = [self._internal_audience_group()] if role == "manage" else []
        return self._access_graph_domain(
            role, exclude_groups=exclude, owner=not exclude_ownership
        )

    def _direct_reach(self, role: str, *, exclude_ownership: bool = False) -> Domain:
        # a document's own reach, a shortcut its target's; the owner of a
        # shortcut edits it while they may read what it points at
        own = Domain("shortcut_document_id", "=", False) & self._graph_reach(
            role, exclude_ownership=exclude_ownership
        )
        target = self._graph_reach(role, exclude_ownership=exclude_ownership)
        shortcut = Domain("shortcut_document_id", "!=", False) & Domain(
            "shortcut_document_id", "any", target
        )
        if not exclude_ownership:
            readable_target = self._graph_reach("view")
            shortcut |= Domain("shortcut_document_id", "!=", False) & (
                Domain("owner_id", "=", self.env.uid)
                & (
                    Domain("shortcut_document_owner_id", "=", self.env.uid)
                    | Domain("shortcut_document_id", "any", readable_target)
                )
            )
        domain = own | shortcut
        if role == "edit" and self._user_is_documents_manager():
            # managers edit wherever the employees' audience reaches, and a
            # shortcut where it reaches the target
            audience = self._access_graph_domain(
                "view",
                groups=[self._internal_audience_group()],
                partner=False,
                owner=False,
            )
            domain |= (Domain("shortcut_document_id", "=", False) & audience) | (
                Domain("shortcut_document_id", "!=", False)
                & Domain("shortcut_document_id", "any", audience)
            )
        return domain

    def _reach(
        self, role: str, ignore_link: bool, *, exclude_ownership: bool = False
    ) -> Domain:
        # the documents reached at the role or above
        domain = self._direct_reach(role, exclude_ownership=exclude_ownership)
        if exclude_ownership or ignore_link:
            return domain
        direct_view = self._direct_reach("view")
        if role == "edit":
            # an edit link raises whoever reaches the document to edit
            domain |= direct_view & Domain("access_via_link", "=", "edit")
        # a document shared by link and not hidden is found at the link's role
        # by whoever reaches its folder
        link_roles = ("view", "edit") if role == "view" else ("edit",)
        domain |= (
            self._permission_company_domain()
            & Domain("access_via_link", "in", link_roles)
            & Domain("is_access_via_link_hidden", "=", False)
            & Domain("folder_id", "any", direct_view)
        )
        return domain

    @api.depends(
        "access_ids.role",
        "access_ids.group_id",
        "access_ids.date_to",
        "access_scope_path",
        "shortcut_document_id.access_internal",
    )
    def _compute_access_internal(self) -> None:
        # a shortcut's audience is its target's
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
        self, fnames: typing.Sequence[str], load: str = "_classic_read"
    ) -> list:
        self._check_content_read(fnames)
        if _PERMISSION_READERS & set(fnames):
            # one permission batch for the records and their folders: read in
            # field order, user_folder_id asked the folders' in a second one,
            # each a pair of reach queries (half the SQL of a kanban load)
            (self | self.folder_id).mapped("user_permission")
        return super()._read_format(fnames, load=load)

    def export_data(self, fields_to_export: list[str]) -> dict[str, list]:
        self._check_content_read([path.split("/")[0] for path in fields_to_export])
        return super().export_data(fields_to_export)

    def _check_content_read(self, fnames: typing.Iterable[str]) -> None:
        # read, search_read, web_read and export hand the file's bytes over
        # RPC as any download route does: the same gate (ir.binary's).
        # Attribute access -- the business code parsing a CFDI, a PDF -- is
        # processing, not handing over. No client key (bin_size) exempts a
        # read: the client decides nothing here, and no view reads these
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
        # Log the INPUTS, not only the refusal. Both of these gates used to be
        # visible in a log only through the caller's `content_refused` event,
        # so an allowed request said nothing -- and "was this blocked document
        # served because the block is off, because the caller is an editor, or
        # because the link is an edit link?" was unanswerable from any log,
        # which is exactly the question a download-block complaint asks.
        if _debug.logic.enabled:
            # the arguments are built only when the channel is on:
            # user_permission alone is two permission searches
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
        # leaving, taking one's own grant away, is anyone's; it narrows no one
        # else's access
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
            # a boundary keeps out what the folders above grant: only what is
            # granted here, the owner and the Documents managers reach it
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
            # the SQL above reached the whole subtree, readable by the writer
            # or not, once the writer's right on the roots was checked: its
            # links follow as the link machinery's, named
            self.browse(link_changed).with_privilege(
                "base.privilege_manage_links",
                reason="a folder's link setting reached its subtree",
            )._sync_document_links(roles=dict.fromkeys(link_changed, access_via_link))

        return changes_by_document_dict

    @api.model
    def _invalidate_permission_cache(self, fields_written: list[str]) -> None:
        # a grant reaches every document below its folder, and the SQL above
        # bypasses `modified()`: every non-stored compute that reads a
        # permission (user_folder_id, user_can_move, display_name, ...) is
        # dropped for the whole model
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

    def _may_manage_access(self) -> bool:
        if self.env.su:
            return True
        privilege = self.env.registry.access_policy.privilege_ids(
            self.env, ("document.privilege_share_documents",)
        )
        if privilege & self.env.privileges:
            return True
        return all(self.mapped("user_can_manage"))

    @api.model
    def _source_ranks(self, sources: list[dict], key_of: Any) -> dict:
        # {key: highest rank} over the access graph's sources: the one fold
        # every "who reaches this, how far" question is; key_of names what is
        # counted (a partner, a grant key) and None skips a source
        roles = self._access_graph.roles
        ranks: dict = {}
        for source in sources:
            if (key := key_of(source)) is not None:
                ranks[key] = max(ranks.get(key, 0), roles.index(source["role"]) + 1)
        return ranks

    def _member_roles(self) -> dict:
        # {partner: role} of every partner a grant or an owner reaches the
        # document with, on it or on a folder above it
        self.check_singleton()
        roles = self._access_graph.roles
        ranks = self._source_ranks(
            (self.shortcut_document_id or self)._access_graph_sources(),
            lambda source: source["partner"] or None,
        )
        return {partner: roles[rank - 1] for partner, rank in ranks.items()}

    @api.model
    def _grant_key(self, partner: Any, group: Any, company: Any) -> tuple:
        # a principal as a grant names it: a partner, or a group within a
        # company or in all of them
        if partner:
            return ("partner", partner.id, False)
        return ("group", group.id, company.id or False)

    def _inherited_ranks(self) -> dict[tuple, int]:
        # {principal key: rank} of every grant or owner above the document
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
        # the document stops inheriting and keeps, as its own grants, what
        # reached it from above, except the principals being lowered
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
        # a boundary made at creation keeps, as its own, what its folder's
        # scope grants to groups: the audience, a module's group
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
        # one principal's own grant on each document: a role at or below what
        # reaches it from above is inherited, one below it makes the document
        # a boundary (decision K1); False removes the grant. Answers the
        # member changes in the shape the access tracking reads
        roles = self._access_graph.roles
        Access = self._sharing().env["document.access"]
        kind, principal_id, company_id = key
        leaving = self._leaving(key)
        changes = []
        for document in self.filtered(lambda d: not d.shortcut_document_id):
            if kind == "partner" and principal_id == document.owner_id.partner_id.id:
                # the owner holds the top role on its document whatever it is
                # granted there: nothing to write, nothing to narrow
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
        # grants are written by who manages the documents, checked before;
        # the privilege lets them write the grant rows
        return self.with_privilege(
            "document.privilege_share_documents",
            reason="whoever manages a document changes who can access it",
        )

    def _leaving(self, key: tuple) -> bool:
        # the user taking their own grant away, without managing the document:
        # the grant goes, what reaches them from above stays
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
