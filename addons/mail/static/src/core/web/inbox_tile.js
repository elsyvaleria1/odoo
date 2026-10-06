// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { deserializeDateTime, toLocaleDateString } from "@web/core/l10n/dates";
import { useService } from "@web/core/utils/hooks";
import { HomeTileRecordLink } from "@web/webclient/home_menu/home_tiles/home_tile_record_link";
import { homeTileRegistry } from "@web/webclient/home_menu/home_tiles/home_tiles";

/**
 * @typedef {{ id: number, author: string, record_name: string, model: string | false, res_id: number | false, date: string, preview: string }} InboxMessage
 */

export class InboxTile extends Component {
    static template = "mail.InboxTile";
    static components = { HomeTileRecordLink };
    static props = {
        data: t.object({ count: t.number(), messages: t.array() }),
        size: t.string(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
    }

    /** @returns {InboxMessage[]} */
    get messages() {
        return this.props.data.messages;
    }

    /** @param {InboxMessage} message */
    dateOf(message) {
        return toLocaleDateString(deserializeDateTime(message.date));
    }

    openInbox() {
        return this.action.doAction({
            type: "ir.actions.client",
            tag: "mail.action_discuss",
            context: { active_id: "discuss.tab_notification" },
        });
    }
}

homeTileRegistry.add("inbox", { Component: InboxTile });
