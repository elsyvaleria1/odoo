/** @odoo-module native */
import { HrUserPreferencesController } from "@hr/views/preferences_form_view";
import { patch } from "@web/core/utils/patch";
import { updateAccountOnMobileDevice } from "@web_mobile/js/core/mixins";

patch(HrUserPreferencesController.prototype, {
    async onRecordSaved() {
        await updateAccountOnMobileDevice();
        return await super.onRecordSaved(...arguments);
    },
});
