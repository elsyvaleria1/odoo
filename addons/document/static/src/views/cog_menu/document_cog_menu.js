/** @odoo-module native */
import { registry } from "@web/core/registry";
import { CogMenu } from "@web/search/cog_menu/cog_menu";
import {
    COG_GROUP,
    COG_MENU_REGISTRY_VALIDATION,
} from "@web/search/cog_menu/cog_menu_group";
import { getDisplayedRegistryItems } from "@web/search/utils/misc";

import { makeDocumentsCogMenuItem } from "./document_cog_menu_item.js";
import { documentCogMenuPinAction } from "./document_cog_menu_pin_actions.js";

export const documentsCogMenuRegistry = registry.category("documents_cog_menu");

documentsCogMenuRegistry.addValidation(COG_MENU_REGISTRY_VALIDATION);

for (const [key, item] of [
    ["download", makeDocumentsCogMenuItem("download", COG_GROUP.DATA)],
    ["rename", makeDocumentsCogMenuItem("rename", COG_GROUP.RECORD)],
    ["share", makeDocumentsCogMenuItem("share", COG_GROUP.RECORD)],
    ["shortcut", makeDocumentsCogMenuItem("shortcut", COG_GROUP.RECORD)],
    ["star", makeDocumentsCogMenuItem("star", COG_GROUP.RECORD)],
    ["details", makeDocumentsCogMenuItem("details", COG_GROUP.RECORD)],
    ["trash", makeDocumentsCogMenuItem("trash", COG_GROUP.RECORD)],
    ["pin-actions", documentCogMenuPinAction],
    ["automations", makeDocumentsCogMenuItem("automations", COG_GROUP.APP)],
]) {
    documentsCogMenuRegistry.add(key, item);
}

export class DocumentsCogMenu extends CogMenu {
    async _registryItems() {
        const [globalItems, documentsItems] = await Promise.all([
            super._registryItems(),
            getDisplayedRegistryItems(documentsCogMenuRegistry, this.viewScope),
        ]);
        return [
            ...globalItems,
            ...documentsItems.map((item) => ({
                ...item,
                key: `documents-${item.key}`,
            })),
        ];
    }
}
