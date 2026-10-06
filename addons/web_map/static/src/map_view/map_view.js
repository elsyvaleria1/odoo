/** @odoo-module native */
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";

import { MapArchParser } from "./map_arch_parser.js";
import { MapController } from "./map_controller.js";
import { MapModel } from "./map_model.js";
import { MapRenderer } from "./map_renderer.js";

export const mapView = {
    type: "map",

    Controller: MapController,
    Renderer: MapRenderer,
    Model: MapModel,
    ArchParser: MapArchParser,

    buttonTemplate: "web_map.MapView.Buttons",
    searchMenuTypes: ["filter", "groupBy", "favorite"],

    modelParams: {
        fromState: (state) => state,
        fromArch: (archInfo, { context, fields, resModel }, config) => ({
            allowResequence: archInfo.allowResequence || false,
            context,
            defaultOrder: archInfo.defaultOrder,
            fieldNames: archInfo.fieldNames,
            fieldNamesMarkerPopup: archInfo.fieldNamesMarkerPopup,
            fields,
            hasFormView: (config.views || []).some((v) => v[1] === "form"),
            hideAddress: archInfo.hideAddress || false,
            hideName: archInfo.hideName || false,
            hideTitle: archInfo.hideTitle || false,
            limit: archInfo.limit || 80,
            numbering: archInfo.routing || false,
            offset: 0,
            panelTitle: archInfo.panelTitle || config.getDisplayName() || _t("Items"),
            resModel,
            resPartnerField: archInfo.resPartnerField,
            routing: archInfo.routing || false,
        }),
    },
};

registry.category("views").add("map", mapView);
