// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";

/**
 * @typedef FlowConnectionClickParams
 * @property {import("./flow_types").FlowConnectionId} connectionId
 * @property {MouseEvent} originalEvent
 */

/**
 * @typedef FlowConnectionProps
 * @property {string} className
 * @property {import("./geometry/connections").FlowConnectionGeometry} geometry
 * @property {string} label
 * @property {(params: FlowConnectionClickParams) => void} onClick
 * @property {boolean} selected
 */

/** @extends {Component<FlowConnectionProps>} */
export class FlowConnection extends Component {
    static template = "web.FlowConnection";
    static props = {
        className: t.string().optional(""),
        geometry: t.object(),
        label: t.string().optional(""),
        onClick: t.function().optional(() => () => {}),
        selected: t.boolean().optional(false),
    };
    props = useProps(this.constructor.props);

    get classNames() {
        return [
            "o_flow_editor_connection",
            this.props.className,
            this.props.selected ? "o_flow_editor_connection_selected" : "",
        ]
            .filter(Boolean)
            .join(" ");
    }

    /** @param {MouseEvent} ev */
    onClick(ev) {
        ev.stopPropagation();
        this.props.onClick({
            connectionId: this.props.geometry.id,
            originalEvent: ev,
        });
    }
}
