/** @odoo-module native */
import { ManualBarcodeScanner } from "@barcodes/components/manual_barcode";
import { markup, onWillStart } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { KanbanRenderer } from "@web/views/kanban";

export class StockBarcodeKanbanRenderer extends KanbanRenderer {
    static template = "stock_barcode.KanbanRenderer";
    setup() {
        super.setup(...arguments);
        this.barcodeService = useService("barcode");
        this.dialogService = useService("dialog");
        this.resModel = this.props.list.model.config.resModel;
        this.displayTransferProtip = this.resModel === "stock.picking";
        onWillStart(this.onWillStart);
    }

    openManualBarcodeDialog() {
        this.dialogService.add(ManualBarcodeScanner, {
            facingMode: "environment",
            onResult: (barcode) => {
                this.barcodeService.bus.trigger("barcode_scanned", { barcode });
            },
            onError: () => {},
        });
    }

    async onWillStart() {
        const groups = [
            "stock.group_tracking_lot",
            "stock.group_production_lot",
            "uom.group_uom",
        ];
        const hasGroups = await Promise.all(groups.map((g) => user.hasGroup(g)));
        this.packageEnabled = hasGroups[0];
        this.trackingEnabled = hasGroups[1];
        this.uomEnabled = hasGroups[2];
    }

    get transferTip() {
        const tags = { bold_s: markup`<b>`, bold_e: markup`</b>` };
        const enabled = [
            this.trackingEnabled && "lot",
            this.packageEnabled && "package",
            this.uomEnabled && "packaging",
        ]
            .filter(Boolean)
            .join(",");
        switch (enabled) {
            case "lot,package,packaging":
                return _t(
                    "Scan a %(bold_s)s transfer%(bold_e)s, a %(bold_s)s product%(bold_e)s, a %(bold_s)s lot%(bold_e)s, a %(bold_s)s packaging%(bold_e)s, or a %(bold_s)s package%(bold_e)s to filter your records",
                    tags,
                );
            case "lot,package":
                return _t(
                    "Scan a %(bold_s)s transfer%(bold_e)s, a %(bold_s)s product%(bold_e)s, a %(bold_s)s lot%(bold_e)s, or a %(bold_s)s package%(bold_e)s to filter your records",
                    tags,
                );
            case "lot,packaging":
                return _t(
                    "Scan a %(bold_s)s transfer%(bold_e)s, a %(bold_s)s product%(bold_e)s, a %(bold_s)s lot%(bold_e)s, or a %(bold_s)s packaging%(bold_e)s to filter your records",
                    tags,
                );
            case "lot":
                return _t(
                    "Scan a %(bold_s)s transfer%(bold_e)s, a %(bold_s)s product%(bold_e)s, or a %(bold_s)s lot%(bold_e)s to filter your records",
                    tags,
                );
            case "package,packaging":
                return _t(
                    "Scan a %(bold_s)s transfer%(bold_e)s, a %(bold_s)s product%(bold_e)s, a %(bold_s)s packaging%(bold_e)s, or a %(bold_s)s package%(bold_e)s to filter your records",
                    tags,
                );
            case "package":
                return _t(
                    "Scan a %(bold_s)s transfer%(bold_e)s, a %(bold_s)s product%(bold_e)s, or a %(bold_s)s package%(bold_e)s to filter your records",
                    tags,
                );
            case "packaging":
                return _t(
                    "Scan a %(bold_s)s transfer%(bold_e)s, a %(bold_s)s product%(bold_e)s, or a %(bold_s)s packaging%(bold_e)s to filter your records",
                    tags,
                );
            default:
                return _t(
                    "Scan a %(bold_s)s transfer%(bold_e)s or a %(bold_s)s product%(bold_e)s to filter your records",
                    tags,
                );
        }
    }
}
