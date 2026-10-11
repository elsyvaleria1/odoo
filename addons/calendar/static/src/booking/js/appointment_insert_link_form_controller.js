/** @odoo-module native */
import { t } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { FormController, formView } from "@web/views/form";

class AppointmentInsertLinkFormController extends FormController {
    static props = {
        ...FormController.props,
        insertLink: t.function(),
        closeDialog: t.function(),
    };
    async beforeExecuteActionButton(clickParams) {
        if (clickParams.special) {
            if (clickParams.special === "save") {
                const saved = await this.model.root.save();
                if (saved) {
                    this.props.insertLink(this.model.root.data.book_url);
                } else {
                    return false;
                }
            }
            this.props.closeDialog();
            return false;
        }
        return super.beforeExecuteActionButton(...arguments);
    }
}
registry.category("views").add("appointment_insert_link_form", {
    ...formView,
    Controller: AppointmentInsertLinkFormController,
});
