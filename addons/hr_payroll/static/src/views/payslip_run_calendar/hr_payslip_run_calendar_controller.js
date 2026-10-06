/** @odoo-module native */
import { CalendarController } from "@web/views/calendar";

import { useOpenPayRun } from "../payslip_run_hook.js";

export class PayRunCalendarController extends CalendarController {
    setup() {
        super.setup();
        this.openPayRun = useOpenPayRun();
    }

    createRecord(record) {
        this.openPayRun({
            date_start: record.start,
            date_end:
                record.end ?? record.start?.add({ months: 1 }).subtract({ days: 1 }),
        });
    }

    async editRecord(record) {
        this.openPayRun({
            id: record.id,
        });
    }
}
