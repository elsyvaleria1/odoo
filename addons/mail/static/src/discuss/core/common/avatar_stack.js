// @ts-check
/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

/**
 * @typedef {Object} Props
 * @prop {(persona: import("models").ResPartner|import("models").MailGuest) => string} [avatarClass]
 * @prop {Array} personas
 * @prop {"v"|"h"} [direction]
 * @prop {number} [max]
 * @prop {number} [size]
 * @extends {Component<Props, import("@web/env").OdooEnv>}
 */
export class AvatarStack extends Component {
    static template = "mail.AvatarStack";
    static props = {
        containerClass: t.string().optional(),
        direction: t
            .customValidator(t.string(), (d) => ["v", "h"].includes(d))
            .optional("h"),
        avatarClass: t.function().optional(() => () => ""),
        max: t.number().optional(4),
        onClick: t.function().optional(() => () => {}),
        personas: t.array(),
        size: t.number().optional(24),
        slots: t.any().optional(),
    };
    props = useProps(this.constructor.props);

    /**
     * @param {number} index
     * @returns {string}
     */
    getStyle(index) {
        const styles = [
            "box-sizing: content-box",
            `height: ${this.props.size}px`,
            "margin: 1px",
            `padding: 1.5px`,
            `width: ${this.props.size}px`,
            `z-index: ${this.props.personas.length - index}`,
        ];
        if (index !== 0) {
            const marginDirection = this.props.direction === "v" ? "top" : "left";
            styles.push(`margin-${marginDirection}: -${this.props.size / 4.5}px`);
        }
        return styles.join(";");
    }
}
