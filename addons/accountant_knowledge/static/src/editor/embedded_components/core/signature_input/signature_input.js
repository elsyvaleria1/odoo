/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";

export class ReadonlySignatureInputComponent extends Component {
    static template = "accountant_knowledge.ReadonlyEmbeddedSignatureInput";
    static props = {};
    props = useProps(this.constructor.props);
}

export const readonlySignatureInputEmbedding = {
    name: "signatureInput",
    Component: ReadonlySignatureInputComponent,
};
