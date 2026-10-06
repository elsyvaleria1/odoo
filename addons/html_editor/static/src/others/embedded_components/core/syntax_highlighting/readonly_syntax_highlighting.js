/** @odoo-module native */
import { Component, onMounted, onWillStart, t, useProps, xml } from "@odoo/owl";
import { useColorSchemeEffect } from "@web/core/color_scheme";

import {
    DEFAULT_LANGUAGE_ID,
    getPreValue,
    highlightPre,
    loadPrism,
} from "./syntax_highlighting_utils.js";

export class ReadonlySyntaxHighlightingComponent extends Component {
    static props = { value: t.string(), languageId: t.string(), host: t.object() };
    static template = xml`<span/>`;
    props = useProps(this.constructor.props);

    setup() {
        onWillStart(() => loadPrism(this.props.host.ownerDocument));
        useColorSchemeEffect(() => loadPrism(this.props.host.ownerDocument));
        onMounted(() => {
            const owlRoot = [...(this.props.host.children || [])].find(
                (child) => child.nodeName === "OWL-ROOT",
            );
            highlightPre(
                owlRoot || this.props.host,
                this.props.value,
                this.props.languageId,
            );
        });
    }
}

export const readonlySyntaxHighlightingEmbedding = {
    name: "readonlySyntaxHighlighting",
    Component: ReadonlySyntaxHighlightingComponent,
    getProps: (host) => ({
        host,
        languageId: host.dataset.languageId || DEFAULT_LANGUAGE_ID,
        value: getPreValue(host),
    }),
};
