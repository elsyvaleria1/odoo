// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useAutoresize } from "@web/core/utils/dom/autoresize";
import { elementRef } from "@web/core/utils/element_ref";
import { useFieldFlush } from "@web/fields/hooks/debounced_field_commit";

const log = makeLogger("web.field.property_text");

export class PropertyText extends Component {
    static template = "web.PropertyText";
    static props = {
        updateProperty: t.function(),
        value: t.string(),
        record: t.object().optional(),
    };
    props = useProps(this.constructor.props);

    /** @type {import("@odoo/owl").Ref} */
    textareaRef;

    setup() {
        this.textareaRef = elementRef();
        useAutoresize(/** @type {any} */ (this.textareaRef));

        if (this.props.record) {
            const flush = (/** @type {Event} */ ev) => {
                const el = /** @type {HTMLTextAreaElement | null} */ (
                    this.textareaRef.el
                );
                if (!el || el !== document.activeElement) {
                    return;
                }
                const typed = el.value !== this.props.value;
                log.logic("flush focused textarea", () => ({
                    input: el.value,
                    value: this.props.value,
                    typed,
                }));
                if (typed) {
                    /** @type {CustomEvent} */ (ev).detail?.proms?.push(
                        this.props.updateProperty({ target: el }),
                    );
                }
            };
            useFieldFlush(this.props.record.model.bus, flush);
        }
    }
}
