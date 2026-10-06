/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class GanttTimeDisplayBadge extends Component {
    static props = {
        reactive: t.object({
            position: t
                .object({
                    top: t.number().optional(),
                    right: t.number().optional(),
                    left: t.number().optional(),
                })
                .optional(),
            class: t.string().optional(),
            text: t.string().optional(),
        }),
    };
    static template = "web_gantt.GanttTimeDisplayBadge";
    props = useProps(this.constructor.props);

    get positionStyle() {
        const { position } = this.props.reactive;
        const style = [`top:${position.top}px`];
        if ("left" in position) {
            style.push(`left:${position.left}px`);
        } else {
            style.push(`right:${position.right}px`);
        }
        return style.join(";");
    }
}
