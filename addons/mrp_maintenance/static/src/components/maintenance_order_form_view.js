/** @odoo-module native */
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { FormController, formView } from "@web/views/form";

class MaintenanceOrderFormController extends FormController {
    setup() {
        super.setup();
        this.notification = useService("notification");
    }

    async onWillSaveRecord(record) {
        this.savingRecordId = record.resId;
        return super.onWillSaveRecord(...arguments);
    }

    async onRecordSaved(record) {
        if (record.resId !== this.savingRecordId) {
            this.notification.add(
                _t("The maintenance order has successfully been created."),
                { type: "success" },
            );
        }
        return super.onRecordSaved(...arguments);
    }
}

export const MaintenanceOrderFormView = {
    ...formView,
    Controller: MaintenanceOrderFormController,
};

registry.category("views").add("maintenance_order_form", MaintenanceOrderFormView);
