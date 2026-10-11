/** @odoo-module native */
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formView } from "@web/views/form";

class EventBoothConfiguratorController extends formView.Controller {
    setup() {
        super.setup();
        this.action = useService("action");
    }

    async onRecordSaved(record) {
        await super.onRecordSaved(...arguments);
        const { event_id, event_booth_category_id, event_booth_ids } = record.data;
        return this.action.doAction({
            type: "ir.actions.act_window_close",
            infos: {
                eventBoothConfiguration: {
                    event_id,
                    event_booth_category_id,
                    event_booth_pending_ids: event_booth_ids.currentIds,
                },
            },
        });
    }
}

registry.category("views").add("event_booth_configurator_form", {
    ...formView,
    Controller: EventBoothConfiguratorController,
});
