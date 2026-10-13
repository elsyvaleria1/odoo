/** @odoo-module native */
import { markup, onMounted } from "@odoo/owl";
import { useBarcodeScreen } from "@stock_barcode/barcode_screen_hook";
import { useBus, useService } from "@web/core/utils/hooks";
import { KanbanController } from "@web/views/kanban";

export class StockBarcodeKanbanController extends KanbanController {
    setup() {
        super.setup(...arguments);
        useBarcodeScreen("kanban", "list_kanban");
        this.barcodeService = useService("barcode");
        useBus(this.barcodeService.bus, "barcode_scanned", (ev) =>
            this._onBarcodeScannedHandler(ev.detail.barcode),
        );
        onMounted(() => {
            document.activeElement.blur();
        });
    }

    openRecord(record) {
        this.actionService.doAction(
            "stock_barcode.stock_barcode_picking_client_action",
            {
                additionalContext: { active_id: record.resId },
            },
        );
    }

    async createRecord() {
        const action = await this.model.orm.call(
            "stock.picking",
            "action_view_new_picking",
            [],
            {
                context: this.props.context,
            },
        );
        if (action) {
            return this.actionService.doAction(action);
        }
        return super.createRecord(...arguments);
    }

    /** @param {String} barcode */
    async _onBarcodeScannedHandler(barcode) {
        const kwargs = { barcode, context: this.props.context };
        const res = await this.model.orm.call(
            this.props.resModel,
            "filter_on_barcode",
            [],
            kwargs,
        );
        const action = res.action;
        if (action) {
            if (action.help) {
                action.help = markup(action.help);
            }
            this.actionService.doAction(action);
        } else if (res.warning) {
            const params = { title: res.warning.title, type: "danger" };
            this.notification.add(res.warning.message, params);
        }
    }
}
