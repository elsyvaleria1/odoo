/** @odoo-module native */
import { registries } from "@odoo/o-spreadsheet";
import { onWillUnmount } from "@odoo/owl";
import { addToRegistryWithCleanup } from "@spreadsheet_edition/bundle/helpers/misc";

import { QualitySpreadsheetPlugin } from "./quality_spreadsheet_plugin.js";

const { corePluginRegistry } = registries;

export function useSpreadsheetQualityControlExtension() {
    addQualitySpreadsheetExtensionWithCleanUp(onWillUnmount);
}

function addQualitySpreadsheetExtensionWithCleanUp(cleanUpHook = () => {}) {
    addToRegistryWithCleanup(
        cleanUpHook,
        corePluginRegistry,
        "quality_check_spreadsheet_plugin",
        QualitySpreadsheetPlugin,
    );
}
