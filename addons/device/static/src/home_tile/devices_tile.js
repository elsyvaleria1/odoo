// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { deserializeDateTime, toLocaleDateTimeString } from "@web/core/l10n/dates";
import { useService } from "@web/core/utils/hooks";
import { HomeTileRecordLink } from "@web/webclient/home_menu/home_tiles/home_tile_record_link";
import { homeTileRegistry } from "@web/webclient/home_menu/home_tiles/home_tiles";

/**
 * @typedef {{ id: number, name: string, state: "disconnected" | "error", last_data: string | false }} SilentDevice
 */

export class DevicesTile extends Component {
    static template = "device.DevicesTile";
    static components = { HomeTileRecordLink };
    static props = {
        data: t.object({
            connected: t.number(),
            disconnected: t.number(),
            error: t.number(),
            devices: t.array(),
        }),
        size: t.string(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
    }

    /** @returns {SilentDevice[]} */
    get devices() {
        return this.props.data.devices.slice(0, this.props.size === "2x1" ? 6 : 3);
    }

    /** @param {SilentDevice} device */
    lastDataOf(device) {
        return device.last_data
            ? toLocaleDateTimeString(deserializeDateTime(device.last_data))
            : "";
    }

    /** @param {"filter_disconnected" | "filter_error" | null} filter */
    openAll(filter) {
        return this.action.doAction("device.action_device_device", {
            additionalContext: filter ? { [`search_default_${filter}`]: 1 } : {},
        });
    }
}

homeTileRegistry.add("devices", { Component: DevicesTile });
