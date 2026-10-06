// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { deserializeDateTime, toLocaleDateTimeString } from "@web/core/l10n/dates";
import { useService } from "@web/core/utils/hooks";
import { HomeTileRecordLink } from "@web/webclient/home_menu/home_tiles/home_tile_record_link";
import { homeTileRegistry } from "@web/webclient/home_menu/home_tiles/home_tiles";

/**
 * @typedef {{ id: number, name: string, start: string, stop: string, allday: boolean, location: string }} AgendaEvent
 */

export class AgendaTile extends Component {
    static template = "calendar.AgendaTile";
    static components = { HomeTileRecordLink };
    static props = {
        data: t.object({ events: t.array(), more: t.boolean() }),
        size: t.string(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
    }

    /** @returns {AgendaEvent[]} */
    get events() {
        return this.props.data.events.slice(0, this.props.size === "2x1" ? 6 : 3);
    }

    get hasMore() {
        return (
            this.props.data.more || this.events.length < this.props.data.events.length
        );
    }

    /** @param {AgendaEvent} event */
    timeOf(event) {
        if (event.allday) {
            return "";
        }
        return toLocaleDateTimeString(deserializeDateTime(event.start), {
            showDate: false,
            showTime: true,
            showSeconds: false,
        });
    }

    openCalendar() {
        return this.action.doAction("calendar.action_calendar_event");
    }
}

homeTileRegistry.add("agenda", { Component: AgendaTile });
