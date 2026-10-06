/** @odoo-module native */
import { getEmbeddedProps } from "@html_editor/others/embedded_component_utils";
import { Component, t, useProps } from "@odoo/owl";

export class ReadonlyAccountReportComponent extends Component {
    static template = "accountant_knowledge.ReadonlyEmbeddedAccountReport";
    static props = { name: t.string(), options: t.object() };
    props = useProps(this.constructor.props);
}

export const readonlyAccountReportEmbedding = {
    name: "accountReport",
    Component: ReadonlyAccountReportComponent,
    getProps: (host) => ({
        ...getEmbeddedProps(host),
    }),
};
