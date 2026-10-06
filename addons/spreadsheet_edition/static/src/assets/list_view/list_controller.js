/** @odoo-module native */
import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";
import { ListController } from "@web/views/list";
import { prepareStaticActionMenuItems } from "@web/views/view_utils";

import { useInsertInSpreadsheet } from "../view_hook.js";

patch(ListController.prototype, {
    setup() {
        super.setup();
        this.insertInSpreadsheet = useInsertInSpreadsheet(() =>
            this.getExportableFields()
                .filter((f) => f.type !== "properties" && !f.relatedPropertyField)
                .filter(
                    (f) =>
                        Object.values(this.archInfo.fieldNodes).find(
                            (fN) => fN.name === f.name,
                        )?.widget !== "handle",
                ),
        );
    },

    getStaticActionMenuItems() {
        return {
            ...super.getStaticActionMenuItems(...arguments),
            ...prepareStaticActionMenuItems({
                insertInSpreadsheet: {
                    isAvailable: () => Boolean(session.can_insert_in_spreadsheet),
                    callback: () => this.insertInSpreadsheet(),
                },
            }),
        };
    },
});
