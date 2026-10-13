/** @odoo-module native */
import { useService } from "@web/core/utils/hooks";
import { ListController } from "@web/views/list";

export class DataCleaningCommonListController extends ListController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notificationService = useService("notification");
    }

    /**
     * @param {import("@web/model/relational_model/record").RelationalRecord} record
     * @returns {number | false}
     */
    getOriginalResId(record) {
        const value = record.data.res_id;
        if (record.fields.res_id.type === "many2one_reference") {
            return value ? value.resId : false;
        }
        return value;
    }

    /** @override */
    openRecord(record) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            views: [[false, "form"]],
            res_model: record.data.res_model_name,
            res_id: this.getOriginalResId(record),
            context: {
                create: false,
                edit: false,
            },
        });
    }

    onUnselectClick() {
        this.discardSelection();
    }
}
