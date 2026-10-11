import base64
import json
import logging
import uuid
from collections import defaultdict
from datetime import timedelta
from typing import Any

import psycopg

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import AccessError, UserError
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.libs.json import loads as json_loads
from odoo.tools import OrderedSet, mute_logger
from odoo.tools.image import image_process

from odoo.addons.spreadsheet.utils.json import extend_serialized_json

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

CollaborationMessage = dict[str, Any]


class MixinSpreadsheet(models.AbstractModel):
    _name = "mixin.spreadsheet"
    _inherit = ["mixin.spreadsheet", "mixin.bus.listener"]

    spreadsheet_snapshot = fields.Binary()
    display_thumbnail = fields.Binary(
        compute="_compute_display_thumbnail",
        inverse="_inverse_display_thumbnail",
    )
    spreadsheet_revision_ids = fields.One2many(
        comodel_name="spreadsheet.revision",
        inverse_name="res_id",
        copy=False,
        domain=lambda self: [("res_model", "=", self._name)],
        groups="base.group_system",
    )
    # The last revision id known by the current transaction.
    # Another concurrent transaction can have saved a revision after this one
    # This means it cannot be blindly used to dispatch a new revision.
    current_revision_uuid = fields.Char(
        compute="_compute_current_revision_uuid",
        compute_sudo=True,
    )

    @api.depends("spreadsheet_revision_ids", "spreadsheet_snapshot", "spreadsheet_data")
    def _compute_current_revision_uuid(self) -> None:
        for spreadsheet in self:
            revisions = spreadsheet.spreadsheet_revision_ids
            if revisions:
                revisions.fetch(["revision_uuid"])
                spreadsheet.current_revision_uuid = revisions[-1].revision_uuid
            else:
                snapshot = spreadsheet._get_spreadsheet_serialized_snapshot()
                if snapshot is False:
                    spreadsheet.current_revision_uuid = False
                else:
                    spreadsheet.current_revision_uuid = json_loads(snapshot).get(
                        "revisionId", "START_REVISION"
                    )

    def write(self, vals):
        if "spreadsheet_binary_data" in vals and not self.env.context.get(
            "preserve_spreadsheet_revisions"
        ):
            _debug.logic("collaborative_data_reset_on_write", records=self)
            self._remove_collaborative_data()
        return super().write(vals)

    def copy(self, default=None):
        default = default or {}

        revisions_to_copy = default.pop("spreadsheet_revision_ids", None)
        new_spreadsheets = super().copy(default)

        is_data_changed = bool(
            default.keys() & {"spreadsheet_data", "spreadsheet_binary_data"}
        )
        _debug.logic(
            "spreadsheet_copied",
            source=self,
            copies=new_spreadsheets,
            data_changed=is_data_changed,
            copy_revisions=revisions_to_copy is None,
        )
        if not is_data_changed:
            if revisions_to_copy is None:
                for old_spreadsheet, new_spreadsheet in zip(
                    self, new_spreadsheets, strict=False
                ):
                    old_spreadsheet._copy_revisions_to(new_spreadsheet)

            new_spreadsheets = new_spreadsheets.with_context(
                preserve_spreadsheet_revisions=True
            )
            for old_spreadsheet, new_spreadsheet in zip(
                self, new_spreadsheets, strict=False
            ):
                new_spreadsheet.spreadsheet_data = old_spreadsheet.spreadsheet_data
        new_spreadsheets._copy_spreadsheet_image_attachments()
        new_spreadsheets._remove_comments_from_data()
        return new_spreadsheets

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]):
        spreadsheets = super().create(vals_list)
        spreadsheets._copy_spreadsheet_image_attachments()
        return spreadsheets

    def _get_spreadsheet_metadata(self, access_token=None):
        self.check_singleton()
        spreadsheet_sudo = self._collaborative_sudo("read", access_token)
        can_write = self._check_collaborative_spreadsheet_access(
            "write", access_token, raise_exception=False
        )
        return {
            "id": spreadsheet_sudo.id,
            "name": spreadsheet_sudo.display_name or "",
            "snapshot_requested": can_write
            and spreadsheet_sudo._is_snapshot_required(),
            "isReadonly": not can_write,
            "default_currency": self.env[
                "res.currency"
            ].get_company_currency_for_spreadsheet(),
            "user_locale": self.env["res.lang"]._get_user_spreadsheet_locale(),
            "company_colors": self._get_context_company_colors(),
            "writable_rec_name_field": self._get_writable_record_name_field(),
        }

    def dispatch_spreadsheet_message(
        self, message: CollaborationMessage, access_token=None
    ):
        """This is the entry point of collaborative editing.
        Collaboration messages arrive here. For each received messages,
        the server decides if it's accepted or not. If the message is
        accepted, it's transmitted to all clients through the "bus.bus".
        Messages which do not update the spreadsheet state (a client moved
        joined or left) are always accepted. Messages updating the state
        require special care.

        Refused messages
        ----------------

        An important aspect of collaborative messages is their order. The server
        checks the order of received messages. If one is out of order, it is refused.
        How does it check the order?
        Each message has a `serverRevisionId` property which is the revision on which
        it should be applied. If it's not equal to the current known revision by the server,
        it is out of order and refused.

        Accepted messages
        -----------------

        If the message is found to be in order, it's accepted and the server registers it.
        The current server revision becomes the revision carried by the message, in the
        `nextRevisionId` property.
        With this strategy, we are guaranteed that all accepted message are ordered.
        See `_save_concurrent_revision`.

        :param message: collaborative message to process
        :return: if the message was accepted or not.
        :rtype: bool
        """
        self.check_singleton()
        _debug.lifecycle(
            "spreadsheet_message_received",
            records=self,
            type=message["type"],
            server_revision=message.get("serverRevisionId"),
            next_revision=message.get("nextRevisionId"),
            client=message.get("clientId"),
            via_token=bool(access_token),
        )

        if message["type"] in ["REMOTE_REVISION", "REVISION_UNDONE", "REVISION_REDONE"]:
            self._check_collaborative_spreadsheet_access("write", access_token)
            with _debug.perf(
                "spreadsheet_revision_dispatched",
                cr=self.env.cr,
                records=self,
                type=message["type"],
                commands=len(message.get("commands", ())),
            ) as span:
                revision = self.sudo()._save_concurrent_revision(
                    message["nextRevisionId"],
                    message["serverRevisionId"],
                    self._prepare_spreadsheet_revision_data(message),
                )
                span.set(accepted=bool(revision))
            if revision:
                self._broadcast_spreadsheet_message(message, revision)
            return bool(revision)
        elif message["type"] == "SNAPSHOT":
            self._check_collaborative_spreadsheet_access("write", access_token)
            return self.sudo()._snapshot_spreadsheet(
                message["serverRevisionId"], message["nextRevisionId"], message["data"]
            )
        elif message["type"] in ["CLIENT_JOINED", "CLIENT_LEFT", "CLIENT_MOVED"]:
            self._check_collaborative_spreadsheet_access("read", access_token)
            self._broadcast_spreadsheet_message(message)
            return True
        _debug.logic(
            "spreadsheet_message_ignored",
            records=self,
            reason="unknown_type",
            type=message["type"],
        )
        return False

    def _copy_revisions_to(self, spreadsheet, up_to_revision_id=False) -> None:
        self._check_collaborative_spreadsheet_access("read")
        if up_to_revision_id:
            revisions = self.sudo().spreadsheet_revision_ids.filtered(
                lambda r: r.id <= up_to_revision_id
            )
        else:
            revisions = (
                self.sudo().with_context(active_test=False).spreadsheet_revision_ids
            )
        copied_revisions = self.env["spreadsheet.revision"]
        parent_revision = self.env["spreadsheet.revision"]
        for revision in revisions:
            commands = self._remove_comments_from_commands(revision.commands)
            parent_revision = revision.copy(
                {
                    "res_model": spreadsheet._name,
                    "res_id": spreadsheet.id,
                    "parent_revision_id": parent_revision.id,
                    "commands": commands,
                }
            )
            copied_revisions |= parent_revision
        _debug.pipeline(
            "spreadsheet_revisions_copied",
            source=self,
            target=spreadsheet,
            up_to_revision=up_to_revision_id,
            revisions=len(copied_revisions),
        )
        spreadsheet._check_collaborative_spreadsheet_access("write")
        spreadsheet.sudo().spreadsheet_revision_ids = copied_revisions

    def save_spreadsheet_snapshot(self, snapshot_data) -> None:
        data_revision_uuid = snapshot_data.get("revisionId")
        snapshot_uuid = str(uuid.uuid4())
        snapshot_data["revisionId"] = snapshot_uuid
        revision = {
            "type": "SNAPSHOT",
            "serverRevisionId": data_revision_uuid,
            "nextRevisionId": snapshot_uuid,
            "data": snapshot_data,
        }
        is_accepted = self.dispatch_spreadsheet_message(revision)
        if not is_accepted:
            _debug.logic(
                "spreadsheet_snapshot_save_refused",
                records=self,
                reason="concurrent_update",
                base_revision=data_revision_uuid,
            )
            raise UserError(
                self.env._(
                    "The operation could not be applied because of a concurrent update. Please try again."
                )
            )

    def _snapshot_spreadsheet(
        self, revision_uuid: str, snapshot_revision_uuid, spreadsheet_snapshot: dict
    ):
        """Save the spreadsheet snapshot along the revision id. Delete previous
        revisions which are no longer needed.
        If the `revision_uuid` is not the same as the server revision, the snapshot is
        not accepted and is ignored.

        :param revision_uuid: the revision on which the snapshot is based
        :param snapshot_revision_uuid: snapshot revision
        :param spreadsheet_snapshot: spreadsheet data
        :return: True if the snapshot was saved, False otherwise
        """
        if snapshot_revision_uuid != spreadsheet_snapshot.get("revisionId"):
            _debug.logic(
                "spreadsheet_snapshot_rejected",
                records=self,
                reason="revision_id_mismatch",
                snapshot_revision=snapshot_revision_uuid,
                data_revision=spreadsheet_snapshot.get("revisionId"),
            )
            raise ValueError("The snapshot revision id does not match the revision id")

        revision = self._save_concurrent_revision(
            snapshot_revision_uuid,
            revision_uuid,
            {"type": "SNAPSHOT_CREATED", "version": 1},
        )
        is_accepted = bool(revision)
        _debug.logic(
            "spreadsheet_snapshot_committed",
            records=self,
            accepted=is_accepted,
            base_revision=revision_uuid,
            snapshot_revision=snapshot_revision_uuid,
        )
        if is_accepted:
            self.spreadsheet_snapshot = base64.b64encode(
                json_dumps_bytes(spreadsheet_snapshot)
            )
            revisions = self.spreadsheet_revision_ids
            _debug.pipeline(
                "spreadsheet_revisions_archived_by_snapshot",
                records=self,
                revisions=len(revisions),
            )
            revisions.active = False
            self._broadcast_spreadsheet_message(
                {
                    "type": "SNAPSHOT_CREATED",
                    "serverRevisionId": revision_uuid,
                    "nextRevisionId": snapshot_revision_uuid,
                },
                revision,
            )
        return is_accepted

    def _get_serialized_spreadsheet_data_body(self, access_token=None):
        # handcraft the json response body, avoiding the need for parsing and re-serializing
        # the spreadsheet file and the revisions, which can be expensive for large files.
        with _debug.perf(
            "spreadsheet_data_body_serialized",
            cr=self.env.cr,
            records=self,
            via_token=bool(access_token),
        ) as span:
            metadata = self._get_spreadsheet_metadata(access_token)

            spreadsheet_sudo = self._collaborative_sudo("read", access_token)

            serialized_metadata = json.dumps(metadata, ensure_ascii=False)
            serialized_snapshot = (
                spreadsheet_sudo._get_spreadsheet_serialized_snapshot()
            )
            revisions = spreadsheet_sudo._get_spreadsheet_serialized_revisions()
            serialized_revisions = "[%s]" % ",".join(revisions)
            body = extend_serialized_json(
                serialized_metadata,
                [
                    ("data", serialized_snapshot),
                    ("revisions", serialized_revisions),
                    (
                        "revisionSequence",
                        str(spreadsheet_sudo._get_revision_sequence()),
                    ),
                ],
            )
            span.set(
                snapshot_chars=len(serialized_snapshot),
                revisions=len(revisions),
                body_chars=len(body),
                readonly=metadata["isReadonly"],
            )
        return body

    def _get_revision_sequence(self) -> int:
        # A revision is inserted only once its parent is committed, so along
        # one spreadsheet's chain the row id only grows: the highest one this
        # transaction sees is the state the data it serves holds.
        self.check_singleton()
        return (
            self.env["spreadsheet.revision"]
            .with_context(active_test=False)
            .search(
                [("res_model", "=", self._name), ("res_id", "=", self.id)],
                order="id desc",
                limit=1,
            )
            .id
            or 0
        )

    def _get_spreadsheet_serialized_snapshot(self):
        snapshot_attachment = (
            self.env["ir.attachment"]
            .with_context(bin_size=False)
            .search(
                [
                    ("res_model", "=", self._name),
                    ("res_field", "=", "spreadsheet_snapshot"),
                    ("res_id", "in", self.ids),
                ]
            )
        )
        _debug.logic(
            "spreadsheet_snapshot_source",
            records=self,
            source="snapshot" if snapshot_attachment else "initial_data",
        )
        if snapshot_attachment:
            return snapshot_attachment.raw.decode() or "{}"
        return self.spreadsheet_data or "{}"

    def _is_snapshot_required(self) -> bool:
        if not self.spreadsheet_revision_ids:
            return False
        last_activity = max(self.spreadsheet_revision_ids.mapped("create_date"))
        is_required = last_activity < fields.Datetime.now() - timedelta(hours=2)
        _debug.logic(
            "spreadsheet_snapshot_requirement",
            records=self,
            required=is_required,
            revisions=len(self.spreadsheet_revision_ids),
            last_activity=last_activity,
        )
        return is_required

    def _save_concurrent_revision(
        self, next_revision_uuid, parent_revision_uuid, commands
    ) -> bool:
        """Save the given revision if no concurrency issue is found.
        i.e. if no other revision was saved based on the same `parent_revision_uuid`
        :param next_revision_uuid: the new revision id
        :param parent_revision_uuid: the revision on which the commands are based
        :param commands: revisions commands
        :return: the saved revision, or an empty recordset when it was refused
        """
        self.check_singleton()
        parent_revision_id = self._get_revision_by_uuid(parent_revision_uuid)
        _debug.logic(
            "spreadsheet_revision_parent_resolved",
            records=self,
            parent_revision=parent_revision_uuid,
            parent=parent_revision_id,
            next_revision=next_revision_uuid,
        )
        try:
            with mute_logger("odoo.db.cursor"), self.env.cr.savepoint():
                return self.env["spreadsheet.revision"].create(
                    {
                        "res_model": self._name,
                        "res_id": self.id,
                        "commands": json_dumps(commands),
                        "parent_revision_id": parent_revision_id.id,
                        "revision_uuid": next_revision_uuid,
                        "create_date": fields.Datetime.now(),
                    }
                )
        except psycopg.IntegrityError:
            # If the creation failed with a unique violation error, it is because the parent_revision_id has already
            # been used. This means that at the same (relative) time, another user has made a modification to the
            # document while this user also modified the document, without knowing about each other modification.
            # We don't need to do anything: when the client that already did the modification will be done, the
            # situation will resolve itself when this client receives the other client's modification.
            _logger.info("Wrong base spreadsheet revision on %s", self)
            _debug.logic(
                "spreadsheet_revision_refused",
                records=self,
                reason="concurrent_parent",
                parent_revision=parent_revision_uuid,
                next_revision=next_revision_uuid,
            )
            return self.env["spreadsheet.revision"]

    def _prepare_spreadsheet_revision_data(self, message: CollaborationMessage) -> dict:
        """Prepare revision data to save in the database from
        the collaboration message.
        """
        message = dict(message)
        message.pop("serverRevisionId", None)
        message.pop("nextRevisionId", None)
        message.pop("clientId", None)
        return message

    def _get_spreadsheet_serialized_revisions(self) -> list[str]:
        """Build spreadsheet collaboration messages from the saved
        revision data"""
        self.check_singleton()
        return self._serialize_revisions(self.spreadsheet_revision_ids)

    @api.readonly
    def get_spreadsheet_revisions_after(
        self, revision_uuid: str, access_token=None
    ) -> list[dict] | None:
        """The collaboration messages a client whose head is `revision_uuid`
        has not received, in order; None when that revision is no longer in
        the history (a restore dropped it), where only a reload catches up."""
        self.check_singleton()
        spreadsheet = self._collaborative_sudo("read", access_token)
        revisions = spreadsheet.with_context(
            active_test=False
        ).spreadsheet_revision_ids.sorted("id")
        head = revisions.filtered(
            lambda revision: revision.revision_uuid == revision_uuid
        )
        if head:
            after = revisions.filtered(lambda revision: revision.id > head.id)
        elif revision_uuid == json_loads(
            spreadsheet._get_spreadsheet_serialized_snapshot()
        ).get("revisionId", "START_REVISION"):
            after = spreadsheet.spreadsheet_revision_ids.sorted("id")
        else:
            return None
        return [
            json_loads(message) for message in spreadsheet._serialize_revisions(after)
        ]

    def _serialize_revisions(self, revisions) -> list[str]:
        result = []
        for revision in revisions:
            server_revision_id = self._get_parent_uuid(revision)
            serialized = extend_serialized_json(
                revision.commands,
                [
                    ("serverRevisionId", f'"{server_revision_id}"'),
                    ("nextRevisionId", f'"{revision.revision_uuid}"'),
                ],
            )
            result.append(serialized)
        return result

    def _collaborative_sudo(self, operation: str, access_token=None):
        # The collaborative data (revisions, snapshot) is read and written past
        # the record rules once the share or record check passed: one place
        # that never elevates without it.
        self._check_collaborative_spreadsheet_access(operation, access_token)
        return self.sudo()

    def _check_collaborative_spreadsheet_access(
        self, operation: str, access_token=None, *, raise_exception=True
    ) -> bool:
        """Check that the user has the right to read/write on the document.
        It's used to ensure that a user can read/write the spreadsheet revisions
        of this document.
        """
        try:
            self._check_spreadsheet_share(operation, access_token)
        except AccessError:
            _debug.logic(
                "spreadsheet_access_denied",
                records=self,
                operation=operation,
                via_token=bool(access_token),
                raising=raise_exception,
            )
            if raise_exception:
                raise
            return False
        return True

    def _check_spreadsheet_share(self, operation, access_token) -> None:
        """Delegates the sharing check to the underlying model which might
        implement sharing in different ways.
        """
        self.check_access(operation)

    def _broadcast_spreadsheet_message(
        self, message: CollaborationMessage, revision=None
    ) -> None:
        """Send the message to the spreadsheet channel. A message that saved a
        revision carries its row id as ``revisionSequence``: a client drops the
        ones its loaded data already holds (``_get_revision_sequence``)."""
        self.check_singleton()
        _debug.pipeline(
            "spreadsheet_message_broadcast",
            records=self,
            type=message.get("type"),
            next_revision=message.get("nextRevisionId"),
        )
        payload = dict(message, id=self.id, model=self._name)
        if revision:
            payload["revisionSequence"] = revision.id
        self._bus_send("spreadsheet", payload)

    def _remove_collaborative_data(self) -> None:
        _debug.lifecycle("spreadsheet_collaborative_data_removed", records=self)
        self.spreadsheet_snapshot = False
        self._check_collaborative_spreadsheet_access("write")
        self.with_context(active_test=False).sudo().spreadsheet_revision_ids.unlink()

    def unlink(self):
        """Override unlink to delete spreadsheet revision. This cannot be
        cascaded, because link is done through (res_model, res_id)."""
        if not self:
            return True
        _debug.lifecycle("spreadsheet_unlinked", records=self)
        self.sudo().with_context(active_test=False).spreadsheet_revision_ids.unlink()
        return super().unlink()

    def action_view_spreadsheet(self):
        raise NotImplementedError(
            "This method is not implemented for model %s." % self._name
        )

    @api.model
    def action_view_new_spreadsheet(self, vals=None):
        spreadsheet = self.create(vals or {})
        return spreadsheet.action_view_spreadsheet()

    @api.readonly
    @api.model
    def get_selector_spreadsheet_models(self):
        selectable_models = []
        for model in self.env:
            if (
                issubclass(self.pool[model], self.pool["mixin.spreadsheet"])
                and self.env[model].has_access("write")
                and self.env[model].has_access("create")
            ):
                selector = self.env[model]._get_spreadsheet_selector()
                if selector:
                    selectable_models.append(selector)
        selectable_models.sort(key=lambda m: m["sequence"])
        _debug.logic(
            "spreadsheet_selector_models",
            models=",".join(m["model"] for m in selectable_models) or "none",
        )
        return selectable_models

    @api.model
    def _get_spreadsheet_selector(self):
        return None

    @api.readonly
    @api.model
    def get_spreadsheets(self, domain=(), offset=0, limit=None) -> dict:
        return {
            "total": self.search_count(domain),
            "records": self.search_read(
                domain,
                ["display_name", "display_thumbnail"],
                offset=offset,
                limit=limit,
            ),
        }

    @api.readonly
    def get_spreadsheet_history(self, from_snapshot=False) -> dict:
        """Fetch the spreadsheet history.
        - if from_snapshot is provided, then provides the last snapshot and the revisions since then
        - otherwise, returns the empty skeleton of the spreadsheet with all the revisions since its creation
        """
        self.check_singleton()
        spreadsheet_sudo = self._collaborative_sudo("read")
        _debug.lifecycle(
            "spreadsheet_history_requested", records=self, from_snapshot=from_snapshot
        )
        initial_date = spreadsheet_sudo.create_date

        if from_snapshot:
            data = spreadsheet_sudo._get_spreadsheet_serialized_snapshot()
            revisions = spreadsheet_sudo.spreadsheet_revision_ids
            snapshot = spreadsheet_sudo.env["ir.attachment"].search(
                [
                    ("res_model", "=", self._name),
                    ("res_id", "=", self.id),
                    ("res_field", "=", "spreadsheet_snapshot"),
                ],
                order="write_date DESC",
                limit=1,
            )
            initial_date = snapshot.write_date
        else:
            data = json_loads(self.spreadsheet_data)
            revisions = spreadsheet_sudo.with_context(
                active_test=False
            ).spreadsheet_revision_ids

        return {
            "name": spreadsheet_sudo.display_name,
            "data": data,
            "revisions": [
                dict(
                    json_loads(rev.commands),
                    id=rev.id,
                    name=rev.name,
                    user=(rev.author_id.id, rev.author_id.name),
                    serverRevisionId=self._get_parent_uuid(rev),
                    nextRevisionId=rev.revision_uuid,
                    timestamp=rev.revision_date,
                )
                for rev in revisions
            ],
            "initial_date": initial_date,
            "default_currency": self.env[
                "res.currency"
            ].get_company_currency_for_spreadsheet(),
        }

    def rename_revision(self, revision_id, name) -> None:
        self.check_singleton()
        self._check_collaborative_spreadsheet_access("write")
        self.env["spreadsheet.revision"].sudo().browse(revision_id).name = name

    def fork_history(
        self, revision_id: int, spreadsheet_snapshot: dict, default: dict | None = None
    ):
        self.check_singleton()
        _debug.lifecycle(
            "spreadsheet_history_forked", records=self, revision=revision_id
        )
        default = default or {}
        default["spreadsheet_revision_ids"] = []
        default["spreadsheet_data"] = self.spreadsheet_data
        new_spreadsheet = self.copy(default)
        self.with_context(active_test=False)._copy_revisions_to(
            new_spreadsheet, revision_id
        )
        new_spreadsheet._copy_spreadsheet_image_attachments()
        new_spreadsheet.spreadsheet_snapshot = base64.b64encode(
            json_dumps_bytes(spreadsheet_snapshot)
        )
        new_spreadsheet.sudo().spreadsheet_revision_ids.active = False
        new_spreadsheet._remove_comments_from_data()
        return new_spreadsheet.action_view_spreadsheet()

    def restore_spreadsheet_version(
        self, revision_id: int, spreadsheet_snapshot: dict
    ) -> dict:
        self.check_singleton()
        self._check_collaborative_spreadsheet_access("write")

        spreadsheet = self.sudo()
        all_revisions = spreadsheet.with_context(
            active_test=False
        ).spreadsheet_revision_ids
        revisions_after = all_revisions.filtered(lambda r: r.id > revision_id)
        _debug.pipeline(
            "spreadsheet_version_restore",
            records=self,
            revision=revision_id,
            revisions_dropped=len(revisions_after),
            revisions_total=len(all_revisions),
        )
        revisions_after.unlink()

        current_revision_uuid = (
            spreadsheet.env["spreadsheet.revision"].browse(revision_id).revision_uuid
        )
        snapshot_revision_uuid = str(uuid.uuid4())
        spreadsheet_snapshot["revisionId"] = snapshot_revision_uuid
        # other collaborative users will receive the snapshot message based on
        # a server revision id they do not expect. This will cause them to reload.
        is_accepted = spreadsheet._snapshot_spreadsheet(
            current_revision_uuid,
            snapshot_revision_uuid,
            spreadsheet_snapshot,
        )
        if not is_accepted:
            _debug.logic(
                "spreadsheet_version_restore_refused",
                records=self,
                reason="concurrent_update",
                revision=revision_id,
            )
            raise UserError(
                self.env._(
                    "The operation could not be applied because of a concurrent update. Please try again."
                )
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "info",
                "message": self.env._("Version restored"),
                "next": self.action_view_spreadsheet(),
            },
        }

    @api.model
    def get_search_view_archs(self, action_xml_ids: list[str]):
        records = [
            self.env.ref(xml_id, raise_if_not_found=False) for xml_id in action_xml_ids
        ]
        actions_data = [
            record._get_action_dict()
            for record in records
            if record and record._name == "ir.actions.act_window"
        ]
        search_views = defaultdict(list)
        for action in actions_data:
            res_model = action["res_model"]
            search_view_id = (
                action["search_view_id"][0] if action["search_view_id"] else False
            )
            views = self.env[res_model].get_views(views=[(search_view_id, "search")])
            search_views[res_model].append(views["views"]["search"]["arch"])
        _debug.pipeline(
            "spreadsheet_search_view_archs",
            requested=len(action_xml_ids),
            found=sum(1 for record in records if record),
            window_actions=len(actions_data),
            models=len(search_views),
        )
        return dict(search_views)

    def _get_context_company_colors(self):
        companies = self.env.companies
        colors = OrderedSet()
        for company in companies:
            colors.add(company.report_config_id.primary_color)
            colors.add(company.report_config_id.secondary_color)
            colors.add(company.email_primary_color)
            colors.add(company.email_secondary_color)
        colors.discard(False)
        return list(colors)

    def _dispatch_command(self, command) -> None:
        self._dispatch_commands([command])

    def _dispatch_commands(self, commands) -> None:
        _debug.pipeline(
            "spreadsheet_server_commands_dispatched",
            records=self,
            commands=len(commands),
            types=",".join(sorted({command["type"] for command in commands})),
        )
        is_accepted = self.dispatch_spreadsheet_message(
            self._prepare_new_revision_data(commands)
        )
        if not is_accepted:
            _debug.logic(
                "spreadsheet_server_commands_refused",
                records=self,
                reason="concurrent_update",
            )
            raise UserError(
                self.env._(
                    "The operation could not be applied because of a concurrent update. Please try again."
                )
            )

    def _prepare_new_revision_data(self, commands) -> dict:
        return {
            "type": "REMOTE_REVISION",
            "serverRevisionId": self.current_revision_uuid,
            "nextRevisionId": str(uuid.uuid4()),
            "commands": commands,
        }

    def _get_revision_by_uuid(self, revision_uuid):
        return (
            self.env["spreadsheet.revision"]
            .with_context(active_test=False)
            .search(
                [
                    ("revision_uuid", "=", revision_uuid),
                    ("res_id", "=", self.id),
                    ("res_model", "=", self._name),
                ],
                limit=1,
            )
        )

    def _get_parent_uuid(self, revision):
        parent_revision = revision.parent_revision_id
        if parent_revision:
            return parent_revision.revision_uuid
        if revision.active:
            # After snapshot: get revisionId from snapshot
            data = self._get_spreadsheet_serialized_snapshot()
        else:
            # Before snapshot: get from initial data
            data = self.spreadsheet_data
        return json_loads(data).get("revisionId", "START_REVISION")

    def _remove_comments_from_data(self) -> None:
        """Deletes comments data from the spreadsheet data and its snapshot"""
        self = self.with_context(preserve_spreadsheet_revisions=True)
        for spreadsheet in self:
            if spreadsheet.spreadsheet_data:
                spreadsheet_data = json_loads(spreadsheet.spreadsheet_data)
                sheets = spreadsheet_data.get("sheets", [])
                if any(sheet.get("comments") != {} for sheet in sheets):
                    for sheet in sheets:
                        sheet["comments"] = {}
                    spreadsheet.spreadsheet_data = json_dumps(spreadsheet_data)
            if spreadsheet.spreadsheet_snapshot:
                spreadsheet_snapshot = json_loads(
                    base64.decodebytes(spreadsheet.spreadsheet_snapshot)
                )
                commented = [
                    sheet
                    for sheet in spreadsheet_snapshot.get("sheets", [])
                    if sheet.get("comments")
                ]
                if commented:
                    for sheet in commented:
                        sheet["comments"] = {}
                    spreadsheet.spreadsheet_snapshot = base64.b64encode(
                        json_dumps_bytes(spreadsheet_snapshot)
                    )

    def _remove_comments_from_commands(self, revision_commands_string):
        """Deletes comments related from the commands"""
        revision_commands = json_loads(revision_commands_string)
        if not isinstance(revision_commands, dict):
            return revision_commands_string

        commands = revision_commands.get("commands", [])
        if not len(commands) > 0:
            return revision_commands_string
        revision_commands["commands"] = [
            command
            for command in commands
            if command["type"]
            not in (
                "ADD_COMMENT_THREAD",
                "DELETE_COMMENT_THREAD",
                "EDIT_COMMENT_THREAD",
            )
        ]
        return json_dumps(revision_commands)

    def _copy_spreadsheet_image_attachments(self) -> None:
        """Ensures the image attachments are linked to the spreadsheet record
        and duplicates them if necessary and updates the spreadsheet data and revisions to
        point to the new attachments."""
        self._check_collaborative_spreadsheet_access("write")
        for spreadsheet in self:
            revisions = (
                spreadsheet.sudo()
                .with_context(active_test=False)
                .spreadsheet_revision_ids
            )
            mapping = {}  # old_attachment_id: new_attachment
            revisions_with_images = revisions.filtered(
                lambda r: "CREATE_IMAGE" in r.commands
            )
            for revision in revisions_with_images:
                data = json_loads(revision.commands)
                commands = data.get("commands", [])
                for command in commands:
                    if command["type"] == "CREATE_IMAGE" and command["definition"][
                        "path"
                    ].startswith("/web/image/"):
                        attachment_copy = spreadsheet._get_spreadsheet_image_attachment(
                            command["definition"]["path"], mapping
                        )
                        if attachment_copy:
                            command["definition"]["path"] = get_attachment_image_src(
                                command["definition"]["path"], attachment_copy
                            )
                revision.commands = json_dumps(data)
            data = (
                json_loads(spreadsheet.spreadsheet_data)
                if spreadsheet.spreadsheet_data
                else {}
            )
            spreadsheet._copy_spreadsheet_images_data(data, mapping)
            if spreadsheet.spreadsheet_snapshot:
                snapshot = json_loads(
                    spreadsheet._get_spreadsheet_serialized_snapshot()
                )
                spreadsheet._copy_spreadsheet_images_data(snapshot, mapping)
            _debug.pipeline(
                "spreadsheet_image_attachments_copied",
                records=spreadsheet,
                revisions_with_images=len(revisions_with_images),
                attachments_copied=len(mapping),
            )
            if mapping:
                spreadsheet.with_context(
                    preserve_spreadsheet_revisions=True
                ).spreadsheet_data = json_dumps(data)
                if spreadsheet.spreadsheet_snapshot:
                    spreadsheet.spreadsheet_snapshot = base64.encodebytes(
                        json_dumps_bytes(snapshot)
                    )

    def _copy_spreadsheet_images_data(self, data, mapping) -> None:
        for sheet in data.get("sheets", []):
            for figure in sheet.get("figures", []):
                if figure["tag"] == "image" and figure["data"]["path"].startswith(
                    "/web/image/"
                ):
                    attachment_copy = self._get_spreadsheet_image_attachment(
                        figure["data"]["path"], mapping
                    )
                    if attachment_copy:
                        figure["data"]["path"] = get_attachment_image_src(
                            figure["data"]["path"], attachment_copy
                        )

    def _get_spreadsheet_image_attachment(self, path: str, mapping):
        try:
            attachment_id = int(path.split("/")[3].split("?", maxsplit=1)[0])
        except ValueError:
            _debug.logic("spreadsheet_image_path_unparsable", records=self, path=path)
            return self.env["ir.attachment"]
        attachment = self.env["ir.attachment"].browse(attachment_id).exists()
        if attachment and (
            attachment.res_model != self._name or attachment.res_id != self.id
        ):
            attachment_copy = mapping.get(attachment_id) or attachment.copy(
                {"res_model": self._name, "res_id": self.id}
            )
            mapping[attachment_id] = attachment_copy
            return attachment_copy
        return self.env["ir.attachment"]

    def _inverse_display_thumbnail(self) -> None:
        for spreadsheet in self:
            value = base64.b64encode(
                image_process(
                    base64.b64decode(spreadsheet.display_thumbnail or ""),
                    (150, 150),
                    crop="center",
                )
            )
            thumbnail = (
                self.sudo()
                .env["ir.attachment"]
                .search(
                    [
                        ("res_model", "=", self._name),
                        ("res_id", "=", spreadsheet.id),
                        ("create_uid", "=", self.env.uid),
                        ("res_field", "=", "display_thumbnail"),
                    ],
                    limit=1,
                )
            )
            _debug.logic(
                "spreadsheet_thumbnail_stored",
                records=spreadsheet,
                action="updated" if thumbnail else "created",
                bytes=len(value),
            )
            if thumbnail:
                thumbnail.datas = value
            else:
                self.env["ir.attachment"].create(
                    {
                        "res_model": self._name,
                        "res_id": spreadsheet.id,
                        "res_field": "display_thumbnail",
                        "datas": value,
                        "name": f"{self._name},{spreadsheet.id},{self.env.uid}",
                    }
                )

    @api.depends_context("uid")
    @api.depends("thumbnail")
    def _compute_display_thumbnail(self) -> None:
        # Spreadsheet thumbnails cannot be computed from their binary data.
        # They should be saved independently.
        spreadsheets = self.filtered(
            lambda d: (
                (d.handler if "handler" in d._fields else "spreadsheet")
                == "spreadsheet"
            )
        )
        thumbnails = (
            spreadsheets.sudo()
            .env["ir.attachment"]
            .search(
                [
                    ("res_model", "=", self._name),
                    ("res_id", "in", spreadsheets.ids),
                    ("res_field", "=", "display_thumbnail"),
                    ("create_uid", "=", spreadsheets.env.uid),
                ]
            )
        )
        thumbnails = {self.browse(tn.res_id): tn.datas for tn in thumbnails}
        for spreadsheet in spreadsheets:
            spreadsheet.display_thumbnail = thumbnails.get(spreadsheet, False)

    def _get_writable_record_name_field(self):
        if self._rec_name and not self._fields[self._rec_name].readonly:
            return self._fields[self._rec_name].name
        return None


def get_attachment_image_src(original_path, attachment_copy) -> str:
    has_access_token = f"access_token={attachment_copy.access_token}" in original_path
    if has_access_token:
        return f"/web/image/{attachment_copy.id}?access_token={attachment_copy.access_token}"
    return f"/web/image/{attachment_copy.id}"
