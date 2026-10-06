/** @odoo-module native */
import { Component, t, useProps, xml } from "@odoo/owl";

import { basicContainerBuilderComponentProps, useBuilderComponent } from "../utils.js";
import { BuilderComponent } from "./builder_component.js";

export class BuilderContext extends Component {
    static template = xml`
        <BuilderComponent>
            <t t-call-slot="default"/>
        </BuilderComponent>
    `;
    static props = { ...basicContainerBuilderComponentProps, slots: t.object() };
    static components = {
        BuilderComponent,
    };
    props = useProps(this.constructor.props);

    setup() {
        useBuilderComponent();
    }
}
