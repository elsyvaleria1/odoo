// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";

import { HomeTileRecordLink } from "./home_tile_record_link.js";
import { homeTileRegistry } from "./home_tiles.js";

/** @typedef {{ res_model: string, res_id: number, display_name: string, model_name: string }} RecentRecord */

export class RecentRecordsTile extends Component {
    static template = "web.RecentRecordsTile";
    static components = { HomeTileRecordLink };
    static props = {
        data: t.object({ records: t.array() }),
        size: t.string(),
    };
    props = useProps(this.constructor.props);

    /** @returns {RecentRecord[]} */
    get records() {
        return this.props.data.records.slice(0, this.props.size === "2x1" ? 8 : 4);
    }
}

homeTileRegistry.add("recent_records", { Component: RecentRecordsTile });
