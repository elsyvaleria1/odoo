from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class IrWebsocket(models.AbstractModel):
    _inherit = "ir.websocket"

    def _bus_channels_by_name(self, names):
        result = super()._bus_channels_by_name(names)
        if not self.env.uid:
            return result
        for name in names:
            if name.startswith("spreadsheet_collaborative_session:"):
                record = self._check_spreadsheet_channel(name)
                result[name] = [record] if record else []
        _debug.pipeline(
            "spreadsheet_bus_channels_added",
            requested=len(names),
            added=sum(bool(result[name]) for name in names),
        )
        return result

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
        model = self.env[model_name]
        if model._abstract or not isinstance(model, self.pool["mixin.spreadsheet"]):
            _debug.logic(
                "spreadsheet_channel_refused",
                reason="not_a_spreadsheet",
                model=model_name,
            )
            return None
        if len(params) == 4:
            access_token = params[3]
        else:
            access_token = None
        record = model.browse(res_id).exists()
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
