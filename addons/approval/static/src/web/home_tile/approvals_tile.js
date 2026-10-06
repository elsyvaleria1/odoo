// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { deserializeDateTime, toLocaleDateString } from "@web/core/l10n/dates";
import { useService } from "@web/core/utils/hooks";
import { HomeTileRecordLink } from "@web/webclient/home_menu/home_tiles/home_tile_record_link";
import { homeTileRegistry } from "@web/webclient/home_menu/home_tiles/home_tiles";

/**
 * @typedef {{ id: number, name: string, category: string, owner: string, deadline: string | false, overdue: boolean }} PendingRequest
 */

export class ApprovalsTile extends Component {
    static template = "approval.ApprovalsTile";
    static components = { HomeTileRecordLink };
    static props = {
        data: t.object({ count: t.number(), overdue: t.number(), requests: t.array() }),
        size: t.string(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
    }

    /** @returns {PendingRequest[]} */
    get requests() {
        return this.props.data.requests.slice(0, this.props.size === "2x1" ? 5 : 3);
    }

    /** @param {PendingRequest} request */
    deadlineOf(request) {
        return request.deadline
            ? toLocaleDateString(deserializeDateTime(request.deadline))
            : "";
    }

    openAll() {
        return this.action.doAction("approval.action_approval_request_to_review");
    }
}

homeTileRegistry.add("approvals", { Component: ApprovalsTile });
