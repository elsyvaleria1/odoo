/** @odoo-module native */
import { ForecastSearchModel } from "@crm/views/forecast_search_model";
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list";

export const forecastListView = {
    ...listView,
    SearchModel: ForecastSearchModel,
};

registry.category("views").add("forecast_list", forecastListView);
