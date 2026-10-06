/** @odoo-module native */
import { registry } from "@web/core/registry";
import { mapView } from "@web_map/map_view/map_view";

import { StockMapModel } from "./map_model.js";
import { StockMapRenderer } from "./map_renderer.js";

export const stockMapView = {
    ...mapView,
    Model: StockMapModel,
    Renderer: StockMapRenderer,
};

registry.category("views").add("stock_map", stockMapView);
