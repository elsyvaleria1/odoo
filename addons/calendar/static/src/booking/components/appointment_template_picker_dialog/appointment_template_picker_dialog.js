/** @odoo-module native */
import { Component, onWillStart, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";

export class AppointmentTemplatePickerDialog extends Component {
    static template = "calendar.booking.AppointmentTemplatePickerDialog";
    static components = { Dialog };
    static props = { close: t.function() };
    props = useProps(this.constructor.props);
    setup() {
        super.setup();
        this.action = useService("action");
        this.orm = useService("orm");

        onWillStart(async () => {
            this.appointmentTypeTemplatesData = await this.orm.call(
                "appointment.type",
                "get_appointment_type_templates_data",
                [],
            );
        });
    }

    async onTemplateClick(templateData) {
        const action = await this.orm.call(
            "appointment.type",
            "action_setup_appointment_type_template",
            [templateData.template_key],
        );
        this.action.doAction(action);
    }
}
