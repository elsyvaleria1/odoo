/** @odoo-module native */
import { Component, markup, onWillStart, t, useProps } from "@odoo/owl";
import {
    DATETIME_MED,
    deserializeDateTime,
    formatDuration,
    toLocaleString,
} from "@web/core/l10n/dates";
import { rpc } from "@web/core/network";
import { Dialog } from "@web/ui/dialog";

export class ExhibitorConnectClosedDialog extends Component {
    static template = "website_event_exhibitor.ExhibitorConnectClosedDialog";
    static components = { Dialog };
    static props = { sponsorId: t.number(), close: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        onWillStart(() => this.fetchSponsor());
    }

    /**
     * @private
     */
    async fetchSponsor() {
        const sponsorData = await rpc(
            `/event_sponsor/${encodeURIComponent(this.props.sponsorId)}/read`,
        );
        sponsorData.website_description = sponsorData.website_description || "";
        sponsorData.website_description = markup(sponsorData.website_description);
        this.formatEventStartRemaining = formatDuration(
            sponsorData.event_start_remaining,
            true,
        );
        this.formatEventDateBegin = toLocaleString(
            deserializeDateTime(sponsorData.event_date_begin, {
                tz: sponsorData.event_date_tz,
            }),
            DATETIME_MED,
        );
        this.sponsorData = sponsorData;
    }
}
