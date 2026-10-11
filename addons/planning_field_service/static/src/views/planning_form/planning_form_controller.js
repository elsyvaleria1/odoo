/** @odoo-module native */
import { PlanningFormController } from "@planning/views/planning_form/planning_form_view";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

const GEOLOCATED_ACTIONS = ["action_sign_in", "action_complete"];

patch(PlanningFormController.prototype, {
    setup() {
        super.setup();
        this.fieldServiceGeolocation = useService("field_service_geolocation");
    },

    async beforeExecuteActionButton(clickParams) {
        if (
            GEOLOCATED_ACTIONS.includes(clickParams.name) &&
            this.model.root.data.user_id?.id === user.userId
        ) {
            clickParams.context = {
                ...clickParams.context,
                geolocation: await this.fieldServiceGeolocation.getGeolocation(),
            };
        }
        return super.beforeExecuteActionButton(clickParams);
    },
});
