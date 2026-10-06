// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { homeTileRegistry } from "@web/webclient/home_menu/home_tiles/home_tiles";

/**
 * @typedef {"ready" | "late" | "waiting"} TransferBucket
 * @typedef {{ id: number, name: string, ready: number, late: number, waiting: number }} OperationType
 */

export class TransfersTile extends Component {
    static template = "stock.TransfersTile";
    static props = {
        data: t.object({
            ready: t.number(),
            late: t.number(),
            waiting: t.number(),
            types: t.array(),
        }),
        size: t.string(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
    }

    /** @returns {OperationType[]} */
    get types() {
        return this.props.data.types.slice(0, this.props.size === "2x1" ? 6 : 3);
    }

    /** @param {TransferBucket} bucket */
    openAll(bucket) {
        return this.action.doAction(`stock.action_picking_tree_${bucket}`);
    }

    /** @param {OperationType} type */
    async open(type) {
        const bucket = type.late ? "late" : "ready";
        const action = await this.orm.call(
            "stock.picking.type",
            `action_view_pickings_${bucket}`,
            [[type.id]],
        );
        return this.action.doAction(action);
    }
}

homeTileRegistry.add("transfers", { Component: TransfersTile });
