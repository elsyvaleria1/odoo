/** @odoo-module native */
import { Img } from "@html_builder/core/img";
import { provideBuilderOptionsContext } from "@html_builder/utils/utils";
import { Component, t, useProps } from "@odoo/owl";

export class CustomizeComponent extends Component {
    static template = "html_builder.CustomizeComponent";
    static components = { Img };
    static props = {
        editingElements: t.array(),
        comp: t.function(),
        compProps: t.object(),
    };
    props = useProps(this.constructor.props);

    setup() {
        provideBuilderOptionsContext(() => this.props.editingElements);
    }
}
