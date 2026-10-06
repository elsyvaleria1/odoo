/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";

import {
    basicContainerBuilderComponentProps,
    useApplyVisibility,
    useSelectableComponent,
    useVisibilityObserver,
} from "../utils.js";
import { BuilderComponent } from "./builder_component.js";

export class BuilderButtonGroup extends Component {
    static template = "html_builder.BuilderButtonGroup";
    static props = {
        ...basicContainerBuilderComponentProps,
        slots: t.object().optional(),
    };
    static components = { BuilderComponent };
    props = useProps(this.constructor.props);

    setup() {
        this.rootRef = elementRef();
        useVisibilityObserver(this.rootRef, useApplyVisibility(this.rootRef));

        useSelectableComponent(this.props.id);
    }
}
