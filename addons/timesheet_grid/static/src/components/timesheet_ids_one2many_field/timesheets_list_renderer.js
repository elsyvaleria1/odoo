/** @odoo-module native */
import { ListRenderer } from "@web/views/list";

export class TimesheetsListRenderer extends ListRenderer {
    async onDeleteRecord(record) {
        if (record.data.is_timer_running) {
            this.props.list.model.root.update({ timer_start: false });
        }
        return await super.onDeleteRecord(record);
    }
}
