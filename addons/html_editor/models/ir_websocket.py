import re

from odoo import models
from odoo.exceptions import AccessError
from odoo.libs.debug_log import DebugLog

from ..tools import collaboration_channel

_debug = DebugLog(__name__)

COLLABORATION_CHANNEL = re.compile(r"editor_collaboration:(\w+(?:\.\w+)*):(\w+):(\d+)")


class IrWebsocket(models.AbstractModel):
    _inherit = "ir.websocket"

    def _get_bus_channels(self, channels):
        if self.env.uid:
            channels = [*channels, *self._collaboration_channels(channels)]
        return super()._get_bus_channels(channels)

    def _collaboration_channels(self, channels):
        # A name this subscriber may not hear is refused alone: raising would
        # fail the whole subscription of the worker, every tab of the browser
        # left hearing nothing.
        for channel in channels:
            if not isinstance(channel, str) or not (
                match := COLLABORATION_CHANNEL.match(channel)
            ):
                continue
            model_name, field_name, res_id = match[1], match[2], int(match[3])
            if self.env.user._is_public() or model_name not in self.env:
                _debug.logic("collaboration_channel_refused", channel=channel[:80])
                continue
            document = self.env[model_name].browse(res_id)
            if not document.exists():
                continue
            try:
                document.check_access("read")
                document.check_access("write")
                if field := document._fields.get(field_name):
                    document._check_field_access(field, "read")
                    document._check_field_access(field, "write")
            except AccessError:
                continue
            yield collaboration_channel(
                self.env.registry.db_name, model_name, field_name, res_id
            )
