/** @odoo-module native */
import { SEARCH_PANEL_UPDATED } from "@document/views/utils";
import { makeLogger } from "@web/core/debug/debug_logger";
import { registry } from "@web/core/registry";
import { useBus } from "@web/core/utils/hooks";
import { useRender } from "@web/core/utils/render_hooks";
import { CogMenu } from "@web/search/cog_menu/cog_menu";
import {
    COG_GROUP,
    COG_MENU_REGISTRY_VALIDATION,
} from "@web/search/cog_menu/cog_menu_group";
import { useSearchModel } from "@web/search/search_model";
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

const log = makeLogger("document.cog_menu");

export class DocumentsCogMenu extends CogMenu {
    setup() {
        super.setup();
        const render = useRender();
        const searchModel = useSearchModel();
        for (const event of ["update", SEARCH_PANEL_UPDATED]) {
            useBus(searchModel, event, async () => {
                await this._refreshRegistryItems(event);
                render();
            });
        }
    }

    async _registryItems() {
        const [globalItems, documentsItems] = await Promise.all([
            super._registryItems(),
            getDisplayedRegistryItems(documentsCogMenuRegistry, this.viewScope),
        ]);
        log.logic("registryItems", () => ({
            global: globalItems.length,
            documents: documentsItems.length,
            folderId: this.viewScope?.searchModel?.getSelectedFolderId?.(),
        }));
        return [
            ...globalItems,
            ...documentsItems.map((item) => ({
                ...item,
                key: `documents-${item.key}`,
            })),
        ];
    }
}
