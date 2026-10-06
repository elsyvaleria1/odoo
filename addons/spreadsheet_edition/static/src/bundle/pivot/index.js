/** @odoo-module native */
import "./autofill.js";

import * as spreadsheet from "@odoo/o-spreadsheet";
import { initCallbackRegistry } from "@spreadsheet/o_spreadsheet/init_callbacks";
import { _t } from "@web/core/translation";

import { insertPivot } from "./pivot_init_callback.js";
import { PivotAutofillPlugin } from "./plugins/pivot_autofill_plugin.js";
import { PivotOdooInsertion } from "./plugins/pivot_odoo_insertion.js";
import { NewPivotSidePanel } from "./side_panels/new_pivot_side_panel/new_pivot_side_panel.js";
import { PivotDetailsSidePanel } from "./side_panels/pivot_details_side_panel.js";

const { featurePluginRegistry, pivotSidePanelRegistry, sidePanelRegistry } =
    spreadsheet.registries;

featurePluginRegistry.add("odooPivotAutofillPlugin", PivotAutofillPlugin);
featurePluginRegistry.add("odooPivotOdooInsertionPlugin", PivotOdooInsertion);

pivotSidePanelRegistry.add("ODOO", {
    editor: PivotDetailsSidePanel,
});

initCallbackRegistry.add("insertPivot", insertPivot);

sidePanelRegistry.add("NewOdooPivotSidePanel", {
    title: _t("New Odoo Pivot"),
    Body: NewPivotSidePanel,
});
