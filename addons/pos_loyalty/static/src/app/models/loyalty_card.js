/** @odoo-module native */
import { Base } from "@point_of_sale/app/models/related_models";
import { compareDates, today } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";

export class LoyaltyCard extends Base {
    static pythonModel = "loyalty.card";

    isExpired() {
        // If no expiration date is set, the card is not expired
        if (!this.expiration_date) {
            return false;
        }

        return compareDates(this.expiration_date, today()) < 0;
    }
}

registry.category("pos_available_models").add(LoyaltyCard.pythonModel, LoyaltyCard);
