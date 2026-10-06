/** @odoo-module native */
import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";
import { KanbanController } from "@web/views/kanban";
import { prepareStaticActionMenuItems } from "@web/views/view_utils";

import { useInsertInSpreadsheet } from "../view_hook.js";

export const patchKanbanControllerExportSelection = {
    setup() {
        super.setup();
        this.insertInSpreadsheet = useInsertInSpreadsheet(() =>
            this.getExportableFields().filter((f) => !f.relatedPropertyField),
        );
    },

    getStaticActionMenuItems() {
        const root = this.model.root;
        const isM2MGrouped = root.groupBy.some((groupBy) => {
            const fieldName = groupBy.split(":")[0];
            return root.fields[fieldName].type === "many2many";
        });
        return {
            ...super.getStaticActionMenuItems(...arguments),
            ...prepareStaticActionMenuItems({
                insertInSpreadsheet: {
                    isAvailable: () =>
                        Boolean(session.can_insert_in_spreadsheet) && !isM2MGrouped,
                    callback: () => this.insertInSpreadsheet(),
                },
            }),
        };
    },
};

export const unpatchKanbanControllerExportSelection = patch(
    KanbanController.prototype,
    patchKanbanControllerExportSelection,
);
