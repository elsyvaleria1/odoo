/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class Many2OneAvatarRankField extends Component {
    static template = "sale_timesheet_enterprise.Many2OneAvatarRankField";
    static props = {
        rank: t.number(),
        id: t.number().optional(0),
        size: t.string().optional("small"),
        class: t.string().optional(""),
    };
    props = useProps(this.constructor.props);

    get imgSrc() {
        return this.props.id === 0
            ? "/hr/static/src/img/default_image.png"
            : `/web/image/hr.employee/${this.props.id}/avatar_128`;
    }

    get rankingClassBorder() {
        if (this.props.rank < 4) {
            return "o-border-" + this.props.rank;
        }
        return "border-primary";
    }

    get rankingClassBackground() {
        if (this.props.rank < 4) {
            return "o-bg-" + this.props.rank;
        }
        return "bg-primary";
    }
}
