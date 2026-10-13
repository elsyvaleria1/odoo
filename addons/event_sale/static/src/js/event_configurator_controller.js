/** @odoo-module native */
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formView } from "@web/views/form";

export class EventConfiguratorController extends formView.Controller {
    setup() {
        super.setup();
        this.action = useService("action");
    }

    /** @override */
    async onRecordSaved(record) {
        await super.onRecordSaved(...arguments);
        const { event_id, event_slot_id, event_ticket_id } = record.data;
        return this.action.doAction({
            type: "ir.actions.act_window_close",
            infos: {
                eventConfiguration: {
                    event_id,
                    event_slot_id,
                    event_ticket_id,
                },
            },
        });
    }
}

registry.category("views").add("event_configurator_form", {
    ...formView,
    Controller: EventConfiguratorController,
});
