import re

from odoo import models
from odoo.exceptions import AccessError
from odoo.libs.debug_log import DebugLog

from ..tools import collaboration_channel

_debug = DebugLog(__name__)

COLLABORATION_CHANNEL = re.compile(r"editor_collaboration:(\w+(?:\.\w+)*):(\w+):(\d+)")


class IrWebsocket(models.AbstractModel):
    _inherit = "ir.websocket"

    def _bus_channels_by_name(self, names):
        result = super()._bus_channels_by_name(names)
        if self.env.uid:
            for name in names:
                if channel := self._collaboration_channel(name):
                    result[name] = [channel]
        return result

    def _collaboration_channel(self, name):
        if not (match := COLLABORATION_CHANNEL.match(name)):
            return None
        model_name, field_name, res_id = match[1], match[2], int(match[3])
        if (
            self.env.user._is_public()
            or model_name not in self.env
            or self.env[model_name]._abstract
            or field_name not in self.env[model_name]._fields
        ):
            _debug.logic("collaboration_channel_refused", channel=name[:80])
            return None
        document = self.env[model_name].browse(res_id)
        if not document.exists():
            return None
        field = document._fields[field_name]
        try:
            document.check_access("read")
            document.check_access("write")
            document._check_field_access(field, "read")
            document._check_field_access(field, "write")
        except AccessError:
            return None
        return collaboration_channel(
            self.env.registry.db_name, model_name, field_name, res_id
        )
