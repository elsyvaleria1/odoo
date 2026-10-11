/** @odoo-module native */
import { DataCleaningCommonListController } from "@data_recycle/views/data_cleaning_common_list";
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list";

export class DataCleaningListController extends DataCleaningCommonListController {
    async onValidateClick() {
        const record_ids = await this.model.root.getResIds(true);
        await this.orm.call("data_cleaning.record", "action_validate", [record_ids]);
        await this.model.load();
    }
}

registry.category("views").add("data_cleaning_list", {
    ...listView,
    Controller: DataCleaningListController,
    buttonTemplate: "DataCleaning.buttons",
});
