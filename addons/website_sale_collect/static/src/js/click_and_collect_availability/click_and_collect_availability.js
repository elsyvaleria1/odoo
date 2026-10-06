/** @odoo-module native */
import { LocationSelectorDialog } from "@delivery/js/location_selector/location_selector_dialog/location_selector_dialog";
import { Component, onWillDestroy, proxy, t, useProps } from "@odoo/owl";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { useEventBus, useService } from "@web/core/utils/hooks";

export class ClickAndCollectAvailability extends Component {
    static template = "website_sale_collect.ClickAndCollectAvailability";
    static props = {
        productId: t.number(),
        active: t.boolean().optional(true),
        zipCode: t.string().optional(),
        selectedLocationData: t.object().optional(),
        inStoreStockData: t.object().optional(),
        deliveryStockData: t.object().optional(),
        showSelectStoreButton: t.boolean().optional(),
    };
    props = useProps(this.constructor.props);
    setup() {
        super.setup();
        this.bus = useEventBus();
        this.dialog = useService("dialog");
        this.state = proxy({
            productId: this.props.productId,
            selectedLocationData: this.props.selectedLocationData,
            inStoreStockData: this.props.inStoreStockData,
            deliveryStockData: this.props.deliveryStockData,
            active: this.props.active,
        });
        const updateState = this._updateStateWithCombinationInfo.bind(this);
        this.bus.addEventListener("updateCombinationInfo", (res) =>
            updateState(res.detail),
        );
        onWillDestroy(() =>
            this.bus.removeEventListener("updateCombinationInfo", updateState),
        );
    }

    /**
     * @private
     * @param {Object} combinationInfo
     * @return {void}
     */
    _updateStateWithCombinationInfo(combinationInfo) {
        this.state.productId = combinationInfo.product_id;
        this.state.inStoreStockData = combinationInfo.in_store_stock_data;
        this.state.deliveryStockData = combinationInfo.delivery_stock_data;
        this.state.active = combinationInfo.is_combination_possible;
    }

    /**
     * @return {void}
     */
    async openLocationSelector() {
        if (!this.state.active) {
            return;
        }
        const { zip_code, id } = this.state.selectedLocationData;
        this.dialog.add(LocationSelectorDialog, {
            isProductPage: true,
            isFrontend: true,
            productId: this.state.productId,
            zipCode: zip_code || this.props.zipCode,
            selectedLocationId: String(id),
            save: async (location) => {
                this.state.selectedLocationData = location;
                this.state.inStoreStockData =
                    location.additional_data.in_store_stock_data;
                const jsonLocation = JSON.stringify(location);
                await rpc("/shop/set_click_and_collect_location", {
                    pickup_location_data: jsonLocation,
                });
            },
        });
    }
}

registry
    .category("public_components")
    .add(
        "website_sale_collect.ClickAndCollectAvailability",
        ClickAndCollectAvailability,
    );
