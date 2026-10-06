/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { pick } from "@web/core/utils/collections/objects";

import {
    basicContainerBuilderComponentProps,
    useBuilderComponent,
    useInputBuilderComponent,
} from "../utils.js";
import { BuilderComponent } from "./builder_component.js";
import {
    BuilderTextInputBase,
    textInputBasePassthroughProps,
} from "./builder_text_input_base.js";

export class BuilderTextInput extends Component {
    static template = "html_builder.BuilderTextInput";
    static props = {
        ...basicContainerBuilderComponentProps,
        ...textInputBasePassthroughProps,
        prefix: t.string().optional(),
        default: t.string().optional(),
    };
    static components = {
        BuilderComponent,
        BuilderTextInputBase,
    };
    props = useProps(this.constructor.props);

    setup() {
        useBuilderComponent();
        const { state, commit, preview } = useInputBuilderComponent({
            id: this.props.id,
            defaultValue: this.props.default,
        });
        this.commit = commit;
        this.preview = preview;
        this.state = state;
    }

    get textInputBaseProps() {
        return pick(this.props, ...Object.keys(textInputBasePassthroughProps));
    }
}
