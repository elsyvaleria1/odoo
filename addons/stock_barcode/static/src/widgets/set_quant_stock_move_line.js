/** @odoo-module native */
import { onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { X2ManyField, x2ManyField } from "@web/fields/relational/x2many";

export class StockBarcodeQuantOne2ManyField extends X2ManyField {
    setup() {
        super.setup();

        onWillStart(async () => {
            this.isQuantSelectable = false;
            const allowedOperationCodes = ["internal", "outgoing", "mrp_operation"];
            const validOperation = allowedOperationCodes.includes(
                this.moveLineData.picking_code,
            );
            if (validOperation) {
                this.isQuantSelectable =
                    (await user.hasGroup("stock.group_production_lot")) ||
                    (await user.hasGroup("stock.group_stock_multi_locations")) ||
                    (await user.hasGroup("stock.group_tracking_lot")) ||
                    (await user.hasGroup("stock.group_tracking_owner"));
            }
        });

        useLayoutEffect(
            () => this._highlightSelectedQuant(),
            () => [this.selectedQuantId, this.quantRecords],
        );
    }

    get moveLineData() {
        return this.props.record.data;
    }

    get quantRecords() {
        return this.moveLineData.product_stock_quant_ids.records;
    }

    get selectedQuantId() {
        const { location_id, trace_id, package_id, owner_id } = this.moveLineData;
        const matchedQuantRecord = this.quantRecords.find(
            ({ data: quant }) =>
                quant.location_id?.id === location_id?.id &&
                quant.trace_id?.id === trace_id?.id &&
                quant.package_id?.id === package_id?.id &&
                quant.owner_id?.id === owner_id?.id,
        );
        return matchedQuantRecord?.data.id || null;
    }

    async openRecord(record) {
        if (this.isQuantSelectable && record.data.id !== this.selectedQuantId) {
            const vals = {
                location_id: record.data.location_id,
                trace_id: record.data.trace_id,
                package_id: record.data.package_id,
                owner_id: record.data.owner_id,
            };
            const { package_id, result_package_id } = this.props.record.data;
            const checkResultPack =
                result_package_id && package_id?.id === result_package_id.id;
            if (
                checkResultPack &&
                record.data.package_id?.id !== result_package_id.id
            ) {
                vals.result_package_id = false;
                vals.outermost_result_package_id = false;
            }
            return await this.props.record.update(vals);
        }
        return;
    }

    _highlightSelectedQuant() {
        const selectedQuantId = this.selectedQuantId;
        this.quantRecords.forEach((quant) => {
            quant.selected = quant.data.id === selectedQuantId;
        });
    }
}

export const stockBarcodeQuantOne2ManyField = {
    ...x2ManyField,
    component: StockBarcodeQuantOne2ManyField,
};

registry
    .category("fields")
    .add("stock_barcode_quant_one2many", stockBarcodeQuantOne2ManyField);
