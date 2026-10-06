// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { HomeTileRecordLink } from "@web/webclient/home_menu/home_tiles/home_tile_record_link";
import { homeTileRegistry } from "@web/webclient/home_menu/home_tiles/home_tiles";

/**
 * @typedef {{ id: number, name: string, partner: string, kind: string }} OpenReview
 */

export class CreditReviewsTile extends Component {
    static template = "account_credit.CreditReviewsTile";
    static components = { HomeTileRecordLink };
    static props = {
        data: t.object({ count: t.number(), reviews: t.array() }),
        size: t.string(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
    }

    /** @returns {OpenReview[]} */
    get reviews() {
        return this.props.data.reviews.slice(0, this.props.size === "2x1" ? 5 : 3);
    }

    openAll() {
        return this.action.doAction("account_credit.action_credit_review", {
            additionalContext: { search_default_open: 1, search_default_mine: 1 },
        });
    }
}

homeTileRegistry.add("credit_reviews", { Component: CreditReviewsTile });
