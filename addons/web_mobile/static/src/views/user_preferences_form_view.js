/** @odoo-module native */
import { registry } from "@web/core/registry";
import { formView } from "@web/views/form";
import { updateAccountOnMobileDevice } from "@web_mobile/js/core/mixins";

class ResUsersPreferenceController extends formView.Controller {
    onRecordSaved(record) {
        return updateAccountOnMobileDevice();
    }
}

registry.category("views").add("res_users_preferences_form", {
    ...formView,
    Controller: ResUsersPreferenceController,
});
