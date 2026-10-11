/** @odoo-module native */
import {
    getEditableDescendants,
    useEditableDescendants,
} from "@html_editor/others/embedded_component_utils";
import {
    EmbeddedComponentToolbar,
    EmbeddedComponentToolbarButton,
} from "@html_editor/others/embedded_components/core/embedded_component_toolbar/embedded_component_toolbar";
import { Component, t, useProps } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/translation";
import { elementRefs } from "@web/core/utils/element_ref";
import { useChildRef } from "@web/core/utils/hooks";
import { usePopover } from "@web/ui/popover";
import { Tooltip } from "@web/ui/tooltip";

export class EmbeddedClipboardComponent extends Component {
    static components = {
        EmbeddedComponentToolbar,
        EmbeddedComponentToolbarButton,
    };
    static props = { host: t.object() };
    static template = "knowledge.EmbeddedClipboard";
    props = useProps(this.constructor.props);

    setup() {
        this.popover = usePopover(Tooltip);
        this.descendantRefs = elementRefs();
        this.descendants = useEditableDescendants(this.props.host, this.descendantRefs);
        this.copyToClipboardButtonRef = useChildRef();
    }

    async onClickCopyToClipboard() {
        const selection = document.getSelection();
        selection.removeAllRanges();
        const range = new Range();
        range.selectNodeContents(this.descendants.clipboardContent);
        selection.addRange(range);
        if (document.execCommand("copy")) {
            this.popover.open(this.copyToClipboardButtonRef.el, {
                tooltip: _t("Content copied to clipboard."),
            });
            browser.setTimeout(this.popover.close, 800);
        }
        selection.removeAllRanges();
    }
}

export const clipboardEmbedding = {
    name: "clipboard",
    Component: EmbeddedClipboardComponent,
    getEditableDescendants: getEditableDescendants,
    getProps: (host) => ({ host }),
};
