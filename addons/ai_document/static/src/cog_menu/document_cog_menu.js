/** @odoo-module native */
import { documentsCogMenuRegistry } from "@document/views/cog_menu/document_cog_menu";
import { DocumentsCogMenuItem } from "@document/views/cog_menu/document_cog_menu_item";
import { user } from "@web/core/user";
import { COG_GROUP } from "@web/search/cog_menu/cog_menu_group";

import { DocumentsCogMenuItemAiAutoSort } from "./document_cog_menu_item_ai_auto_sort.js";

documentsCogMenuRegistry.add("ai-auto-sort", {
    Component: DocumentsCogMenuItemAiAutoSort,
    groupNumber: COG_GROUP.APP,
    isDisplayed: (env) =>
        user.isSystem &&
        DocumentsCogMenuItem.isVisible(
            env,
            ({ folder }) => typeof folder.id === "number",
        ),
});
