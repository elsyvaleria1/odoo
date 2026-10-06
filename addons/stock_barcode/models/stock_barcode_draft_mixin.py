from odoo import api, models
from odoo.api import NewId
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class StockBarcodeDraftMixin(models.AbstractModel):
    """A barcode operation opened before it exists: the client works on its draft values,
    and the first save that has something to write creates it. Opening and leaving one
    therefore writes nothing and consumes no sequence number."""

    _name = "stock.barcode.draft.mixin"
    _description = "Barcode operation created by its first save"

    # The values a client may hand back for a record it has not created yet.
    _barcode_draft_fields = frozenset()
    _barcode_client_action = None

    @api.model
    def _action_open_barcode_draft(self, values, confirm=False):
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            self._barcode_client_action
        )
        draft = {"values": values, "confirm": confirm}
        return dict(action, context={"active_id": False, "barcode_draft": draft})

    @api.model
    def _parse_barcode_draft(self, draft) -> tuple:
        values = {
            name: value
            for name, value in (draft or {}).get("values", {}).items()
            if name in self._barcode_draft_fields
        }
        self._check_barcode_draft_values(values)
        return values, bool((draft or {}).get("confirm"))

    @api.model
    def _check_barcode_draft_values(self, values) -> None:
        return

    @api.model
    def _get_stock_barcode_draft_data(self, draft):
        values, _confirm = self._parse_barcode_draft(draft)
        # `new()` takes no defaults, `create()` does: without them a draft read differently
        # from the record its first save creates (a batch had no state).
        defaults = self.default_get(list(self._fields))
        data = self.new({**defaults, **values})._get_stock_barcode_data()
        for record in data["records"].get(self._name, []):
            if isinstance(record["id"], NewId):
                record["id"] = False
        return data

    @api.model
    def _create_from_barcode_draft(self, draft):
        values, confirm = self._parse_barcode_draft(draft)
        _debug.lifecycle("barcode_draft_create", model=self._name, fields=len(values))
        record = self.create(values)
        if confirm:
            record.action_confirm()
        return record
