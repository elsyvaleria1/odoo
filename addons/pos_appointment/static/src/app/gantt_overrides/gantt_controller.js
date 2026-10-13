/** @odoo-module native */
import { AppointmentBookingGanttController } from "@calendar_gantt/views/gantt/gantt_controller";
import { FormViewDialog } from "@web/views/view_dialogs";

export class POSAppointmentBookingGanttController extends AppointmentBookingGanttController {
    /** @override */
    openDialog(props, options = {}) {
        return super.openDialog(props, options, FormViewDialog);
    }
}
