from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class IrWebsocket(models.AbstractModel):
    _inherit = "ir.websocket"

    def _get_bus_channels(self, channels):
        if self.env.uid:
            channels = self._add_spreadsheet_collaborative_bus_channels(channels)
        return super()._get_bus_channels(channels)

    def _add_spreadsheet_collaborative_bus_channels(self, channels):
        """Add collaborative bus channels for active spreadsheets.

        Listening to channel "spreadsheet_collaborative_session:{res_model}:{res_id}"
        or "spreadsheet_collaborative_session:{res_model}:{res_id}:{access_token}"
        tells the server the spreadsheet is active. But only users with read access
        can actually read the associate bus messages.
        We manually add the channel if the user has read access.
        This channel is used to safely send messages to allowed users.

        :param channels: bus channels
        :return: channels
        """
        requested = list(channels)
        channels = list(requested)
        for channel in requested:
            if not isinstance(channel, str):
                continue
            if channel.startswith("spreadsheet_collaborative_session:"):
                record = self._check_spreadsheet_channel(channel)
                if record:
                    channels.append(record)
        _debug.pipeline(
            "spreadsheet_bus_channels_added",
            requested=len(requested),
            added=len(channels) - len(requested),
        )
        return channels

    def _check_spreadsheet_channel(self, channel):
        params = channel.split(":")
        try:
            res_id = int(params[2])
        except IndexError, ValueError:
            _debug.logic(
                "spreadsheet_channel_refused", reason="malformed", channel=channel
            )
            return None
        model_name = params[1]
        if model_name not in self.env:
            _debug.logic(
                "spreadsheet_channel_refused", reason="unknown_model", model=model_name
            )
            return None
        if len(params) == 4:
            access_token = params[3]
        else:
            access_token = None
        record = self.env[model_name].browse(res_id).exists()
        access = record._check_collaborative_spreadsheet_access(
            "read", access_token, raise_exception=False
        )
        _debug.logic(
            "spreadsheet_channel_checked",
            record=record,
            via_token=access_token is not None,
            granted=access,
        )
        if not access:
            return None
        return record
