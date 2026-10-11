// @ts-check
/** @odoo-module native */

import { useIncidentJourney } from "@error_incident/incident_journey";
import { ErrorDialog } from "@web/components/errors";
import { ClientErrorDialog } from "@web/components/errors/error_dialogs";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

patch(ErrorDialog.prototype, {
    setup() {
        super.setup();
        const internal = user.isInternalUser;
        const occurrence = internal
            ? (this.props.data?.context?.error_incident?.occurrence ?? null)
            : null;
        this.incidentJourney = useIncidentJourney(occurrence);
        this.incidentAction = user.isSystem ? useService("action") : null;
        if (occurrence) {
            this.incidentJourney.start();
        } else if (
            internal &&
            this instanceof ClientErrorDialog &&
            this.props.traceback
        ) {
            this.incidentJourney.report(this.props.traceback);
        }
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
