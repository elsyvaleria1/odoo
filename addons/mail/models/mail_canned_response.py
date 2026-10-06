import typing
from collections import defaultdict
from typing import Literal, Self

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import AccessError, ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL

from odoo.addons.mail.tools.discuss import Store, StoreFieldsInput

if typing.TYPE_CHECKING:
    from odoo.addons.bus.models.res_groups import ResGroups

_debug = DebugLog(__name__)


class MailCannedResponse(models.Model):
    _name = "mail.canned.response"
    _description = "Canned Response"
    _order = "id desc"
    _rec_name = "source"

    source = fields.Char(
        string="Shortcut",
        index="trigram",
        required=True,
        help="Canned response that will automatically be substituted with longer content in your messages."
        " Type '::' followed by the name of your shortcut (e.g. ::hello) to use in your messages.",
    )
    substitution = fields.Text(
        required=True,
        help="Content that will automatically replace the shortcut of your choosing. This content can still be adapted before sending your message.",
    )
    last_used = fields.Datetime(help="Last time this canned_response was used")
    group_ids: ResGroups = fields.Many2many(
        comodel_name="res.groups",
        string="Authorized Groups",
        domain=lambda self: [("id", "in", self.env.user.all_group_ids.ids)],
    )
    is_shared = fields.Boolean(
        string="Determines if the canned_response is currently shared with other users",
        compute="_compute_is_shared",
        store=True,
    )
    is_editable = fields.Boolean(
        string="Determines if the canned response can be edited by the current user",
        compute="_compute_is_editable",
    )

    @api.depends("group_ids")
    def _compute_is_shared(self) -> None:
        for canned_response in self:
            canned_response.is_shared = bool(canned_response.group_ids)

    @api.depends_context("uid")
    @api.depends("create_uid")
    def _compute_is_editable(self) -> None:
        creating = self.filtered(lambda c: not c.id)
        updating = self - creating
        editable = creating._filtered_access("create") + updating._filtered_access(
            "write"
        )
        editable.is_editable = True
        (self - editable).is_editable = False

    @api.constrains("group_ids")
    def _check_group_ids_internal(self) -> None:
        if shared := self._external_groups(self.group_ids):
            raise ValidationError(
                self.env._(
                    "A canned response is shared with internal groups only, not "
                    "%(groups)s.",
                    groups=", ".join(shared.mapped("name")),
                )
            )

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        res = super().create(vals_list)
        res._check_group_ids_joinable(res.group_ids)
        res._broadcast()
        return res

    def write(self, vals: ValuesType) -> Literal[True]:
        groups_before = {}
        if "group_ids" in vals:
            groups_before = {response.id: response.group_ids for response in self}
            self._broadcast(add_deletion=True)
        res = super().write(vals)
        if groups_before:
            added = self.env["res.groups"]
            for response in self:
                added |= response.group_ids - groups_before[response.id]
            self._check_group_ids_joinable(added)
        self._broadcast()
        return res

    def _external_groups(self, groups: ResGroups) -> ResGroups:
        group_user = self.env.ref("base.group_user")
        return groups.filtered(lambda group: group_user not in group.all_implied_ids)

    def _check_group_ids_joinable(self, groups: ResGroups) -> None:
        if self.env.su or not (foreign := groups - self.env.user.all_group_ids):
            return
        _debug.logic("groups_refused", canned_responses=self.ids, groups=foreign.ids)
        raise AccessError(
            self.env._(
                "You can only share a canned response with groups you belong to, "
                "not %(groups)s.",
                groups=", ".join(foreign.mapped("name")),
            )
        )

    def unlink(self) -> Literal[True]:
        self._broadcast(add_deletion=True)
        return super().unlink()

    def _broadcast(self, /, *, add_deletion: bool = False) -> None:
        responses_by_channel = defaultdict(self.browse)
        for canned_response in self:
            for group in canned_response.group_ids - self._external_groups(
                canned_response.group_ids
            ):
                responses_by_channel[group] |= canned_response
            for user in self.env.user | canned_response.create_uid:
                if not user.all_group_ids & canned_response.group_ids:
                    responses_by_channel[user] |= canned_response
        _debug.lifecycle(
            "broadcast",
            canned_responses=self.ids,
            add_deletion=add_deletion,
            targets=len(responses_by_channel),
        )
        for channel, canned_responses in responses_by_channel.items():
            store = Store(bus_channel=channel)
            if add_deletion:
                store.add_deletion(canned_responses)
            else:
                store.add(canned_responses)
            store.bus_send()

    def _to_store_defaults(self, target: Store.Target) -> StoreFieldsInput:
        return ["source", "substitution"]

    @api.model
    def _register_usage(self, canned_response_ids: object) -> None:
        ids = [
            cid
            for cid in (canned_response_ids or [])
            if isinstance(cid, int) and not isinstance(cid, bool)
        ]
        if not ids:
            return
        ids = self.browse(ids)._filtered_access("read").ids
        if not ids:
            return
        _debug.lifecycle("usage_registered", canned_responses=ids)
        self.env.cr.execute(
            SQL(
                """
                UPDATE mail_canned_response SET last_used = %(last_used)s
                WHERE id IN (
                    SELECT id FROM mail_canned_response WHERE id = ANY(%(ids)s)
                    FOR NO KEY UPDATE SKIP LOCKED
                )
                """,
                last_used=fields.Datetime.now(),
                ids=ids,
            )
        )
