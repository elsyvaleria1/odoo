/** @odoo-module native */
import { Component, onMounted, onWillDestroy, t, useProps } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { elementRef } from "@web/core/utils/element_ref";
import {
    applyTextHighlight,
    getCurrentTextHighlight,
    textHighlightFactory,
} from "@website/js/highlight_utils";

const log = makeLogger("website.builder.option.highlight_picker");

export class HighlightPicker extends Component {
    static template = "website.highlightPicker";
    static props = {
        selectHighlight: t.function(),
        previewHighlight: t.function(),
        revertHighlight: t.function(),
        style: t.string().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        useLifecycleLog(log);
        const root = (this.root = elementRef());
        onMounted(() => {
            const endApplyHighlights = log.perf("apply preview highlights");
            for (const textEl of root.el.querySelectorAll(".o_text_highlight")) {
                const highlightId = getCurrentTextHighlight(textEl);
                applyTextHighlight(textEl, highlightId);
            }
            endApplyHighlights(() => ({
                count: root.el.querySelectorAll(".o_text_highlight").length,
            }));
        });

        onWillDestroy(() => {
            this.props.revertHighlight();
        });
    }
    getHighlightFactory() {
        return textHighlightFactory;
    }
}
