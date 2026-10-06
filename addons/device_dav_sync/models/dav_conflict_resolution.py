import logging

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import frozendict

_logger = logging.getLogger(__name__)


class DAVConflictResolution(models.AbstractModel):
    _name = "dav.conflict.resolution"
    _description = "DAV Conflict Resolution"

    @api.model
    def has_conflict(self, sync_state, client_etag, server_etag) -> bool:
        if not sync_state or not client_etag:
            return False

        clean_client_etag = client_etag.strip('"')
        clean_server_etag = server_etag.strip('"')
        clean_synced_etag = (sync_state.etag or "").strip('"')

        if clean_client_etag != clean_server_etag:
            if clean_synced_etag != clean_server_etag:
                _logger.warning(
                    "Conflict detected for %s #%s: client=%s, server=%s, synced=%s",
                    sync_state.resource_model,
                    sync_state.resource_id,
                    clean_client_etag,
                    clean_server_etag,
                    clean_synced_etag,
                )
                return True

        return False

    @api.model
    def resolve_conflict(
        self,
        sync_state,
        server_record,
        client_data,
        strategy="server_wins",
    ):
        if not server_record.exists():
            _logger.info(
                "Conflict resolution: Server record deleted, using client data for %s #%s",
                sync_state.resource_model,
                sync_state.resource_id,
            )
            return {
                "action": "update_server",
                "record": server_record,
                "message": "Server record deleted, client data will be used",
            }

        if strategy == "server_wins":
            return self._resolve_server_wins(sync_state, server_record)
        if strategy == "client_wins":
            return self._resolve_client_wins(sync_state, server_record, client_data)
        if strategy == "merge":
            return self._resolve_merge(sync_state, server_record, client_data)
        if strategy == "manual":
            return self._resolve_manual(sync_state, server_record, client_data)
        raise UserError(
            self.env._("Unknown conflict resolution strategy: %s") % strategy
        )

    def _resolve_server_wins(self, sync_state, server_record) -> dict:
        _logger.info(
            "Conflict resolved (server wins): Keeping server version for %s #%s",
            sync_state.resource_model,
            sync_state.resource_id,
        )

        server_etag = sync_state._get_etag(server_record)
        sync_state.write(
            {
                "etag": server_etag,
                "last_modified": server_record.write_date or server_record.create_date,
                "sync_status": "synced",
                "error_message": False,
            }
        )

        return {
            "action": "keep_server",
            "record": server_record,
            "message": "Server version preserved (server wins strategy)",
        }

    def _resolve_client_wins(self, sync_state, server_record, client_data) -> dict:
        _logger.info(
            "Conflict resolved (client wins): Updating server with client data for %s #%s",
            sync_state.resource_model,
            sync_state.resource_id,
        )

        server_record.write(client_data)

        new_etag = sync_state._get_etag(server_record)
        sync_state.write(
            {
                "etag": new_etag,
                "last_modified": fields.Datetime.now(),
                "sync_status": "synced",
                "error_message": False,
            }
        )

        return {
            "action": "update_server",
            "record": server_record,
            "message": "Server updated with client version (client wins strategy)",
        }

    def _resolve_merge(self, sync_state, server_record, client_data) -> dict:
        _logger.info(
            "Conflict resolved (merge): Merging server and client data for %s #%s",
            sync_state.resource_model,
            sync_state.resource_id,
        )

        merged_data = {
            field: value
            for field, value in client_data.items()
            if value is not None and field in server_record._fields
        }

        if merged_data:
            server_record.write(merged_data)

        new_etag = sync_state._get_etag(server_record)
        sync_state.write(
            {
                "etag": new_etag,
                "last_modified": fields.Datetime.now(),
                "sync_status": "synced",
                "error_message": False,
            }
        )

        return {
            "action": "update_server",
            "record": server_record,
            "message": f"Merged server and client changes ({len(merged_data)} fields updated)",
        }

    def _resolve_manual(self, sync_state, server_record, client_data) -> dict:
        _logger.info(
            "Conflict marked for manual resolution: %s #%s",
            sync_state.resource_model,
            sync_state.resource_id,
        )

        server_data = {
            field: server_record[field]
            for field in client_data
            if field in server_record._fields
        }

        sync_state.write(
            {
                "sync_status": "conflict",
                "error_message": "Manual conflict resolution required",
            }
        )

        return {
            "action": "manual_review",
            "record": server_record,
            "message": "Conflict requires manual resolution",
            "conflict_data": {
                "server": server_data,
                "client": client_data,
                "fields_changed": list(client_data.keys()),
            },
        }


class DAVSyncState(models.Model):
    _inherit = "dav.sync.state"
    _access_anchors = frozendict(
        {
            "owner": "user_id",
        }
    )

    conflict_resolution_strategy = fields.Selection(
        selection=[
            ("server_wins", "Server Wins"),
            ("client_wins", "Client Wins"),
            ("merge", "Merge Changes"),
            ("manual", "Manual Review"),
        ],
        default="server_wins",
        help="Strategy to use when conflicts are detected",
    )
