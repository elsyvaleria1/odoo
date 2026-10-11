/** @odoo-module native */
import { onWillDestroy } from "@odoo/owl";
import {
    provideProductCatalogContext,
    useProductCatalogContext,
} from "@product/product_catalog/product_catalog_context";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { useDebounced } from "@web/core/utils/timing";
import { useSearchModel } from "@web/search/search_model";
import { KanbanRecord } from "@web/views/kanban";

import { ProductCatalogOrderLine } from "./order_line/order_line.js";

export const productCatalogOrderLines = registry.category(
    "product_catalog_order_lines",
);

export const productCatalogKanbanRecordProps = { ...KanbanRecord.props };

export class ProductCatalogKanbanRecord extends KanbanRecord {
    static props = productCatalogKanbanRecordProps;
    static template = "ProductCatalogKanbanRecord";
    static components = {
        ...KanbanRecord.components,
        ProductCatalogOrderLine,
    };

    setup() {
        super.setup();
        this.searchModel = useSearchModel();
        this.debouncedUpdateQuantity = useDebounced(
            this._updateQuantity.bind(this),
            500,
            {
                execBeforeUnmount: true,
            },
        );
        this._pendingUpdate = Promise.resolve();

        const parentCatalog = useProductCatalogContext();
        parentCatalog.productCatalogPendingUpdates?.add(this);
        onWillDestroy(() => parentCatalog.productCatalogPendingUpdates?.delete(this));

        provideProductCatalogContext({
            currencyId: this.props.record.context.product_catalog_currency_id,
            orderId: this.props.record.context.order_id,
            orderResModel: this.props.record.context.product_catalog_order_model,
            digits: this.props.record.context.product_catalog_digits,
            displayUoM: this.props.record.context.display_uom,
            precision: this.props.record.context.precision,
            productId: this.props.record.resId,
            addProduct: this.addProduct.bind(this),
            removeProduct: this.removeProduct.bind(this),
            increaseQuantity: this.increaseQuantity.bind(this),
            setQuantity: this.setQuantity.bind(this),
            decreaseQuantity: this.decreaseQuantity.bind(this),
            childField: this.props.record.context.child_field,
        });
        this.catalogContext = useProductCatalogContext();
    }

    get orderLineComponent() {
        return productCatalogOrderLines.get(
            this.catalogContext.orderResModel,
            ProductCatalogOrderLine,
        );
    }

    get productCatalogData() {
        return this.props.record.productCatalogData;
    }

    onGlobalClick(ev) {
        if (ev.target.closest(".o_product_catalog_cancel_global_click")) {
            return;
        }
        if (this.productCatalogData.quantity === 0) {
            this.addProduct();
        } else {
            this.increaseQuantity();
        }
    }

    async _updateQuantity() {
        const price = await this._updateQuantityAndGetPrice();
        this.productCatalogData.price = parseFloat(price);
    }

    /**
     * Run any debounced quantity write now and resolve once it has landed.
     *
     * @returns {Promise<any>}
     */
    flushPendingUpdate() {
        this.debouncedUpdateQuantity.cancel(true);
        return this._pendingUpdate;
    }

    _updateQuantityAndGetPrice() {
        this._pendingUpdate = this._pendingUpdate
            .catch(() => {})
            .then(() =>
                rpc(
                    "/product/catalog/update_order_line_info",
                    this._getUpdateQuantityAndGetPriceParams(),
                ),
            );
        return this._pendingUpdate;
    }

    get sectionIdOfPendingUpdate() {
        return this._sectionIdOfPendingUpdate === undefined
            ? this.searchModel.selectedSection.sectionId
            : this._sectionIdOfPendingUpdate;
    }

    _getUpdateQuantityAndGetPriceParams() {
        return {
            order_id: this.catalogContext.orderId,
            product_id: this.catalogContext.productId,
            quantity: this.productCatalogData.quantity,
            res_model: this.catalogContext.orderResModel,
            child_field: this.catalogContext.childField,
            section_id: this.sectionIdOfPendingUpdate,
        };
    }

    notifyLineCountChange(lineCountChange) {
        this.searchModel.trigger("section-line-count-change", {
            sectionId: this.sectionIdOfPendingUpdate,
            lineCountChange: lineCountChange,
        });
    }

    updateQuantity(quantity) {
        this._sectionIdOfPendingUpdate = this.searchModel.selectedSection.sectionId;
        if (this.productCatalogData.readOnly) {
            return;
        }
        const lineCountChange = (quantity > 0) - (this.productCatalogData.quantity > 0);
        if (lineCountChange !== 0) {
            this.notifyLineCountChange(lineCountChange);
        }
        this.productCatalogData.quantity = Math.max(0, quantity || 0);
        this.debouncedUpdateQuantity();
    }

    addProduct(qty = 1) {
        if (
            this.productCatalogData.quantity === 0 &&
            qty < this.productCatalogData.min_qty
        ) {
            qty = this.productCatalogData.min_qty;
        }
        this.updateQuantity(qty);
    }

    removeProduct() {
        this.updateQuantity(0);
    }

    increaseQuantity(qty = 1) {
        this.updateQuantity(this.productCatalogData.quantity + qty);
    }

    /**
     * Set the quantity of the product on the order line.
     *
     * @param {Event} event
     */
    setQuantity(event) {
        const quantity = parseFloat(event.target.value);
        this.updateQuantity(Number.isNaN(quantity) ? 0 : quantity);
    }

    decreaseQuantity() {
        this.updateQuantity(this.productCatalogData.quantity - 1);
    }
}
