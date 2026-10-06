/** @odoo-module native */
import {
    getEditableDescendants,
    getEmbeddedProps,
    useEditableDescendants,
} from "@html_editor/others/embedded_component_utils";
import { Component, proxy, t, useProps } from "@odoo/owl";
import { elementRefs } from "@web/core/utils/element_ref";

export class ReadonlyFoldableSection extends Component {
    static template = "knowledge.ReadonlyEmbeddedFoldableSection";
    static props = { host: t.object(), showContent: t.boolean().optional() };
    props = useProps(this.constructor.props);
    setup() {
        this.descendantRefs = elementRefs();
        this.editableDescendants = useEditableDescendants(
            this.props.host,
            this.descendantRefs,
        );
        this.state = proxy({
            showContent: this.props.showContent,
        });
    }
    onInputChange(ev) {
        this.state.showContent = ev.target.checked;
    }
}

export const readonlyFoldableSectionEmbedding = {
    name: "foldableSection",
    Component: ReadonlyFoldableSection,
    getProps: (host) => ({ host, ...getEmbeddedProps(host) }),
    getEditableDescendants: getEditableDescendants,
};
