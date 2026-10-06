/** @odoo-module native */
import { components } from "@odoo/o-spreadsheet";

import { CommonOdooChartConfigPanel } from "../common/config_panel.js";

const { GeoChartRegionSelectSection } = components;

export class OdooGeoChartConfigPanel extends CommonOdooChartConfigPanel {
    static template = "spreadsheet_edition.OdooGeoChartConfigPanel";
    static components = {
        ...CommonOdooChartConfigPanel.components,
        GeoChartRegionSelectSection,
    };
}
