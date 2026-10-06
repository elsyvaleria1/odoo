/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

import { Img } from "../img.js";
import {
    clickableBuilderComponentProps,
    useActionInfo,
    useSelectableItemComponent,
} from "../utils.js";
import { BuilderComponent } from "./builder_component.js";

export class BuilderButton extends Component {
    static template = "html_builder.BuilderButton";
    static components = { BuilderComponent, Img };
    static props = {
        ...clickableBuilderComponentProps,
        title: t.string().optional(),
        label: t.string().optional(),
        iconImg: t.string().optional(),
        iconImgAlt: t.string().optional(),
        icon: t.string().optional(),
        className: t.string().optional(),
        classActive: t.string().optional(),
        style: t.string().optional(),
        type: t.string().optional("secondary"),
        slots: t.object().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.info = useActionInfo();
        const { state, operation } = useSelectableItemComponent(this.props.id);
        this.state = state;
        this.onClick = operation.commit;
        this.onPointerEnter = operation.preview;
        this.onPointerLeave = operation.revert;
    }

    get className() {
        let className = this.props.className || "";
        if (this.props.type) {
            className += ` btn-${this.props.type}`;
        }
        if (this.state.isActive) {
            className = `active ${className}`;
            if (this.props.classActive) {
                className += ` ${this.props.classActive}`;
            }
        }
        if (this.props.icon) {
            className += ` o-hb-btn-has-icon`;
        }
        if (this.props.iconImg) {
            className += ` o-hb-btn-has-img-icon`;
        }
        return className;
    }

    get iconClassName() {
        if (this.props.icon.startsWith("fa-")) {
            return `fa ${this.props.icon}`;
        } else if (this.props.icon.startsWith("oi-")) {
            return `oi ${this.props.icon}`;
        }
        return "";
    }
}
