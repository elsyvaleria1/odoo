// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { useAppContext } from "@web/core/app_context";
import { useService } from "@web/core/utils/hooks";
import { homeTileRegistry } from "@web/webclient/home_menu/home_tiles/home_tiles";

import { activityGroupOpener } from "./activity_group_opener.js";

/**
 * @typedef {import("./activity_group_opener.js").ActivityGroup & { subkey: string, icon: string | false, overdue: number, today: number, planned: number }} ActivityGroup
 */

export class ActivitiesTile extends Component {
    static template = "mail.ActivitiesTile";
    static props = {
        data: t.object({
            overdue: t.number(),
            today: t.number(),
            planned: t.number(),
            groups: t.array(),
        }),
        size: t.string(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
        this.appContext = useAppContext();
    }

    /** @returns {ActivityGroup[]} */
    get groups() {
        return this.props.data.groups.slice(0, this.props.size === "2x1" ? 6 : 3);
    }

    openAll() {
        return this.action.doAction("mail.mail_activity_action_my");
    }

    /** @param {ActivityGroup} group */
    open(group) {
        const filter = group.overdue || group.today ? "all" : "upcoming_all";
        return activityGroupOpener.open(this.appContext, group, filter);
    }
}

homeTileRegistry.add("activities", { Component: ActivitiesTile });
