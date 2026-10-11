import typing

from odoo import models
from odoo.fields import Domain
from odoo.tools import SQL

from odoo.addons.base.models.mixin_access_graph_reach import (
    GROUP,
    OWN,
    USER,
    principal_key,
)

TARGET = 1
LINK = 2
EDIT_LINK = 3
SHORTCUT_OWNER = 4
SHORTCUT_OWN = 5
SYSTEM = 6

LINKED = ("view", "edit")

if typing.TYPE_CHECKING:
    from odoo.tools import Query


class DocumentsDocument(models.Model):
    _inherit = "document.document"

    def _access_reach_tracked_columns(self) -> list[str]:
        return [
            *super()._access_reach_tracked_columns(),
            "shortcut_document_id",
            "access_via_link",
            "is_access_via_link_hidden",
        ]

    def _access_reach_graph_vias(self) -> tuple[int, ...]:
        return (OWN, SHORTCUT_OWN)

    def _access_reach_own_via(self) -> SQL:
        return SQL(
            "CASE WHEN scope.shortcut_document_id IS NULL THEN %s ELSE %s END",
            OWN,
            SHORTCUT_OWN,
        )

    def _access_reach_graph_needs(self) -> list[SQL]:
        linked = SQL(
            "scope.access_via_link = ANY(%s) AND scope.is_access_via_link_hidden IS NOT TRUE",
            list(LINKED),
        )
        return [
            SQL(
                "SELECT shortcut_document_id FROM scope WHERE shortcut_document_id IS NOT NULL"
            ),
            SQL(
                "SELECT folder_id FROM scope WHERE folder_id IS NOT NULL AND %s", linked
            ),
            SQL(
                """SELECT folder.shortcut_document_id
                     FROM scope JOIN document_document AS folder ON folder.id = scope.folder_id
                    WHERE folder.shortcut_document_id IS NOT NULL AND %s""",
                linked,
            ),
        ]

    def _access_reach_ctes(self) -> list[tuple[str, SQL]]:
        top = len(self._access_graph.roles)
        return [
            (
                "direct",
                SQL(
                    """SELECT graph.resource_id, graph.key, graph.rank, graph.node_company_id,
                              graph.grant_id, graph.grant_resource_id
                         FROM graph JOIN document_document AS node_row ON node_row.id = graph.resource_id
                        WHERE node_row.shortcut_document_id IS NULL
                       UNION ALL
                       SELECT node_row.id, graph.key, graph.rank, graph.node_company_id,
                              graph.grant_id, graph.grant_resource_id
                         FROM needed
                         JOIN document_document AS node_row ON node_row.id = needed.id
                         JOIN graph ON graph.resource_id = node_row.shortcut_document_id
                       UNION ALL
                       SELECT node_row.id, node_row.owner_id::int8 * 4 + %(user)s, %(top)s::int2,
                              NULL::int4, NULL::int4, NULL::int4
                         FROM needed
                         JOIN document_document AS node_row ON node_row.id = needed.id
                         JOIN document_document AS target ON target.id = node_row.shortcut_document_id
                        WHERE node_row.owner_id = target.owner_id""",
                    user=USER,
                    top=top,
                ),
            )
        ]

    def _access_reach_derived(self) -> list[SQL]:
        top = len(self._access_graph.roles)
        system = SQL(
            """(SELECT res_id FROM ir_model_data
                 WHERE module = 'document' AND name = 'group_documents_system')"""
        )
        return [
            SQL(
                """SELECT scope.id, graph.key, %(via)s::int2, graph.rank, graph.node_company_id,
                          NULL::int4, scope.owner_id, graph.grant_id, graph.grant_resource_id
                     FROM scope JOIN graph ON graph.resource_id = scope.shortcut_document_id""",
                via=TARGET,
            ),
            SQL(
                """SELECT scope.id, scope.owner_id::int8 * 4 + %(user)s, %(via)s::int2,
                          %(top)s::int2, NULL::int4, NULL::int4, NULL::int4, NULL::int4,
                          NULL::int4
                     FROM scope JOIN document_document AS target ON target.id = scope.shortcut_document_id
                    WHERE scope.owner_id = target.owner_id""",
                user=USER,
                via=SHORTCUT_OWNER,
                top=top,
            ),
            SQL(
                """SELECT scope.id, direct.key, %(via)s::int2,
                          (CASE scope.access_via_link WHEN 'edit' THEN 2 ELSE 1 END)::int2,
                          direct.node_company_id, scope.company_id, NULL::int4,
                          direct.grant_id, direct.grant_resource_id
                     FROM scope JOIN direct ON direct.resource_id = scope.folder_id
                    WHERE scope.access_via_link = ANY(%(linked)s)
                      AND scope.is_access_via_link_hidden IS NOT TRUE""",
                via=LINK,
                linked=list(LINKED),
            ),
            SQL(
                """SELECT scope.id, direct.key, %(via)s::int2, 2::int2, direct.node_company_id,
                          NULL::int4, NULL::int4, direct.grant_id, direct.grant_resource_id
                     FROM scope JOIN direct ON direct.resource_id = scope.id
                    WHERE scope.access_via_link = 'edit'""",
                via=EDIT_LINK,
            ),
            SQL(
                """SELECT scope.id, system.id::int8 * 4 + %(group)s, %(via)s::int2, %(top)s::int2,
                          scope.company_id, NULL::int4, root.owner_id, NULL::int4, NULL::int4
                     FROM scope
                     CROSS JOIN (SELECT %(system)s AS id) AS system
                     JOIN document_document AS root
                       ON root.id = split_part(scope.parent_path, '/', 1)::int4
                    WHERE system.id IS NOT NULL""",
                group=GROUP,
                via=SYSTEM,
                top=top,
                system=system,
            ),
        ]

    def _access_reach_readers(self, affected: SQL) -> list[SQL]:
        return [
            SQL(
                "SELECT id FROM document_document WHERE shortcut_document_id = ANY(%s)",
                affected,
            ),
            SQL(
                """SELECT id FROM document_document
                    WHERE folder_id = ANY(%s) AND access_via_link = ANY(%s)
                      AND is_access_via_link_hidden IS NOT TRUE""",
                affected,
                list(LINKED),
            ),
        ]


    def _folds_system_reach(self) -> bool:
        permissions, guards = self.env["ir.access"]._bound_access_infos(
            self._name, "system_reach"
        )
        shipped = self.env.ref(
            "document.access_document_system_reach", raise_if_not_found=False
        )
        if guards or len(permissions) != 1 or not shipped:
            return False
        row, companies = permissions[0]
        return (
            row.id == shipped.id
            and companies is None
            and row.reach == "predicate"
            and row.predicate[0] == "document.outside_others_drives"
            and row.predicate[2] == "_access_predicate_outside_others_drives"
            and not row.predicate_args
        )

    def _permission_reach(
        self,
        role: str,
        *,
        links: bool,
        exclude_ownership: bool = False,
        system: bool = False,
    ) -> Domain:
        user = self.env.user
        in_use = sorted(self.env.companies.ids)
        vias = [OWN, TARGET, SHORTCUT_OWNER]
        if links:
            vias += [LINK, EDIT_LINK]
        alternatives = []
        if role == "edit" and self._user_is_documents_manager():
            audience = self._internal_audience_group()
            alternatives.append(
                (
                    [principal_key(GROUP, audience)],
                    SQL(
                        """(kind = %(group)s AND pid = %(audience)s AND via = ANY(%(vias)s)
                            AND (date_to IS NULL OR date_to > now() AT TIME ZONE 'UTC')
                            AND (grant_company_id IS NULL OR grant_company_id = ANY(%(in_use)s))
                            AND (node_company_id IS NULL OR node_company_id = ANY(%(in_use)s)))""",
                        group=GROUP,
                        audience=audience,
                        vias=[OWN, TARGET],
                        in_use=in_use,
                    ),
                )
            )
        if system:
            system_group = self.env.ref("document.group_documents_system").id
            alternatives.append(
                (
                    [principal_key(GROUP, system_group)],
                    SQL(
                        """(via = %(via)s AND kind = %(group)s AND pid = %(system)s
                            AND (resource_user_id IS NULL OR resource_user_id = %(uid)s)
                            AND (node_company_id IS NULL OR node_company_id = ANY(%(in_use)s)
                                 OR NOT node_company_id = ANY(%(active)s)))""",
                        via=SYSTEM,
                        group=GROUP,
                        system=system_group,
                        uid=user.id,
                        in_use=in_use,
                        active=user.with_context(active_test=False)
                        .company_ids.filtered("active")
                        .ids,
                    ),
                )
            )
        subquery = self._access_reach_subquery(
            role,
            vias=vias,
            owner=not exclude_ownership,
            owner_vias=() if exclude_ownership else (TARGET,),
            alternatives=alternatives,
        )

        def to_sql(model: models.BaseModel, alias: str, query: Query | None) -> SQL:
            model._access_graph_flush()
            reach = SQL("(%s)", subquery) if query is None else query.once_set(subquery)
            return SQL("%s IN %s", SQL.identifier(alias, "id"), reach)

        return Domain.custom(to_sql=to_sql)
