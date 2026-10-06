/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { useSelfOrder } from "@pos_self_order/app/services/self_order_service";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";

import { useScrollShadow } from "../../utils/scroll_shadow_hook.js";
export class EatingLocationPage extends Component {
    static template = "pos_self_order.EatingLocationPage";
    static props = {};
    props = useProps(this.constructor.props);

    setup() {
        this.selfOrder = useSelfOrder();
        this.router = useService("router");
        this.scrollContainerRef = elementRef();
        this.scrollShadow = useScrollShadow(this.scrollContainerRef);
    }

    onClickBack() {
        this.router.navigate("default");
    }

    selectPreset(preset) {
        this.selfOrder.currentOrder.setPreset(preset);
        this.router.navigate("product_list");
    }

    // In the self, we don't want to display presets that have service_at table. Except if the clients are in
    // restaurant (they scanned QR Code and have a table_identifier in the URL) or if the self is in KioskMode.
    get presets() {
        const all = this.selfOrder.models["pos.preset"].getAll();
        return this.router.getTableIdentifier() != null || this.selfOrder.kioskMode
            ? all
            : all.filter((item) => item.service_at !== "table");
    }
}
