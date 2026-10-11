/** @odoo-module native */
import { proxy } from "@odoo/owl";
import MainComponent from "@stock_barcode/components/main";
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";
import { ConfirmationDialog } from "@web/ui/dialog";

import BarcodeMRPModel from "../models/barcode_mrp_model.js";
import HeaderComponent from "./header.js";

patch(MainComponent.prototype, {
    setup() {
        super.setup();
        this.state = proxy({ ...this.state, displayByProduct: false });
    },

    get displayActionButtons() {
        return super.displayActionButtons && !this.state.displayByProduct;
    },

    get displayOperationButtons() {
        return super.displayOperationButtons || this.model.displayRegisterByProduct;
    },

    get headerFormViewProps() {
        return {
            resId: this.resId || this.model.record.id,
            resModel: this.resModel,
            context: Object.assign(
                { set_qty_producing: true },
                this.props.action.context,
            ),
            viewId: this.model.headerViewId,
            display: { controlPanel: false },
            type: "form",
            onSave: (record) => this.saveFormView(record),
            onDiscard: () => this.toggleBarcodeLines(),
        };
    },

    get lineFormViewProps() {
        const res = super.lineFormViewProps;
        const params = { newByProduct: this.state.displayByProduct };
        res.context = this.model._getNewLineDefaultContext(params);
        return res;
    },

    get lines() {
        return this.model.groupedLines;
    },

    get addLineBtnName() {
        if (this.model.resModel === "mrp.production" && this.model.record.product_id) {
            return _t("Add Component");
        }
        return super.addLineBtnName;
    },

    exit(ev) {
        if (this.state.view === "barcodeLines" && this.state.displayByProduct) {
            this.state.displayByProduct = false;
            this.model.displayByProduct = false;
        } else {
            super.exit(...arguments);
        }
    },

    async cancel() {
        if (this.resModel === "mrp.production") {
            await new Promise((resolve) => {
                this.dialog.add(ConfirmationDialog, {
                    body: _t(
                        "Are you sure you want to cancel this manufacturing order?",
                    ),
                    title: _t("Cancel manufacturing order?"),
                    cancel: () => {},
                    confirm: async () => {
                        await this.orm.call(this.resModel, "action_cancel", [
                            [this.model.resId],
                        ]);
                        resolve();
                    },
                });
            });
            this.model._cancelNotification();
            this._exit();
            return;
        }
        await super.cancel(...arguments);
    },

    async toggleHeaderView() {
        await this.model.save();
        this.changeView("headerProductPage");
    },

    openByProductLines() {
        this._editedLineParams = undefined;
        this.state.displayByProduct = true;
        this.model.displayByProduct = true;
    },

    onOpenProductPage(line) {
        if (this.resModel === "mrp.production" && !this.model.record.product_id) {
            this.toggleHeaderView();
            return;
        }
        return super.onOpenProductPage(...arguments);
    },

    async onWillStart() {
        await super.onWillStart();
        if (this.resModel === "mrp.production") {
            const { default_picking_type_id } = this.props.action.context;
            this.model.picking_type_id = default_picking_type_id;
        }
    },

    async saveFormView(lineRecord) {
        if (lineRecord.resModel === "mrp.production") {
            const prev_qty_producing = this.model.record.qty_producing;
            const curr_qty_producing = lineRecord.data.qty_producing;
            const is_product_form = !this.model.record.product_id;
            const recordId = lineRecord.resId;
            const update = Boolean(this.resId);
            if (!this.resId) {
                this.resId = recordId;
                await this.model.confirmAndSetData(recordId);
                this.toggleBarcodeLines();
            }
            if (!is_product_form && prev_qty_producing !== curr_qty_producing) {
                await this.orm.call("mrp.production", "set_qty_producing", [
                    [recordId],
                ]);
                await this._onRefreshState({ recordId });
            }
            if (update) {
                if (lineRecord.data.product_qty !== this.model.record.product_qty) {
                    await this.orm.call(this.resModel, "action_assign", [[this.resId]]);
                }
                this._onRefreshState({ recordId });
            }
            return;
        }
        return super.saveFormView(...arguments);
    },

    async _onRefreshByProducts() {
        const { route, params } = this.model.getActionRefresh(this.resId);
        const result = await rpc(route, params);
        await this.model.resetState(result.data.records);
        this.openByProductLines();
    },

    onValidateByProduct() {
        this.state.displayByProduct = false;
        this.model.displayByProduct = false;
        this.toggleBarcodeLines();
    },

    _getBarcodeModel() {
        if (this.resModel === "mrp.production") {
            return BarcodeMRPModel;
        }
        return super._getBarcodeModel(...arguments);
    },

    _getHeaderHeight() {
        const headerHeight = super._getHeaderHeight();
        const mo_header = document.querySelector(".o_header");
        return mo_header ? headerHeight + mo_header.offsetHeight : headerHeight;
    },
});

MainComponent.components.Header = HeaderComponent;
