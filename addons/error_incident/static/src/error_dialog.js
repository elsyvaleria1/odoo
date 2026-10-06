// @ts-check
/** @odoo-module native */

import {ErrorDialog} from "@web/components/errors";
import {user} from "@web/core/user";
import {useService} from "@web/core/utils/hooks";
import {patch} from "@web/core/utils/patch";
import {useIncidentJourney} from "@error_incident/incident_journey";

patch(ErrorDialog.prototype, {
    setup() {
        super.setup();
        /* The server names the occurrence on every unexpected error a request
         * raises (`ir.http._capture_request_error`); other errors carry none.
         * Internal users only: the route refuses the rest anyway. */
        const occurrence = user.isInternalUser
            ? (this.props.data?.context?.error_incident?.occurrence ?? null)
            : null;
        this.incidentJourney = useIncidentJourney(occurrence);
        this.incidentAction = user.isSystem ? useService("action") : null;
        this.incidentJourney.start();
    },

    openIncident() {
        this.props.close();
        this.incidentAction?.doAction({
            type: "ir.actions.act_window",
            res_model: "error.incident",
            res_id: this.incidentJourney.state.incident,
            views: [[false, "form"]],
        });
    },
});
