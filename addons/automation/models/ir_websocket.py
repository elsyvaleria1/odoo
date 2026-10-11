from odoo import models

CHANNEL_PREFIX = "automation.workflow/"
SUBCHANNEL = "WORKFLOW"


class IrWebsocket(models.AbstractModel):
    _inherit = "ir.websocket"

    def _bus_channels_by_name(self, names):
        result = super()._bus_channels_by_name(names)
        rule_ids = {}
        for name in names:
            if name.startswith(CHANNEL_PREFIX):
                suffix = name[len(CHANNEL_PREFIX) :]
                if suffix.isascii() and suffix.isdigit():
                    rule_ids[name] = int(suffix)
        if rule_ids:
            readable = (
                self.env["automation.rule"]
                .browse(sorted(set(rule_ids.values())))
                .exists()
                ._filtered_access("read")
            )
            for name, rule_id in rule_ids.items():
                rule = readable.filtered(lambda r, rid=rule_id: r.id == rid)
                result[name] = [(rule, SUBCHANNEL)] if rule else []
        return result
