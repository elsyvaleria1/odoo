/** @odoo-module native */
import { _t } from "@web/core/translation";
import { CalendarController } from "@web/views/calendar";

export class EventSlotCalendarController extends CalendarController {
    getQuickCreateFormViewProps(record) {
        return {
            ...super.getQuickCreateFormViewProps(record),
            onRecordSaved: () => this.model.load(),
            title: _t("New Slot"),
        };
    }
}
