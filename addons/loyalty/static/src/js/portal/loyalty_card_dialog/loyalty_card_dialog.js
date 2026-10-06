/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { deserializeDate, formatDate } from "@web/core/l10n/dates";
import { Dialog } from "@web/ui/dialog";

export class PortalLoyaltyCardDialog extends Component {
    static components = { Dialog };
    static template = "loyalty.portal_loyalty_card_dialog";
    static props = null;
    props = useProps(this.constructor.props);

    get formattedExpirationDate() {
        return formatDate(deserializeDate(this.props.card.expiration_date));
    }
}
