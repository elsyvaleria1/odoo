/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { useAutoresize } from "@web/core/utils/dom/autoresize";
import { elementRef } from "@web/core/utils/element_ref";

export class CustomFieldCard extends Component {
    static template = "sale_pdf_quote_builder.customFieldCard";
    static props = {
        name: t.string(),
        value: t.string(),
        onChange: t.function(),
        readonly: t.boolean().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.customFormFieldTextAreaRef = elementRef();
        this.placeholder = _t("Click to write content for the PDF quote...");
        useAutoresize(this.customFormFieldTextAreaRef);
    }

    expandTextArea(ev) {
        const textarea = ev.target;
        textarea.style.height = textarea.scrollHeight + "px";
    }
}
