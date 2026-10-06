/** @odoo-module native */
import {
    applyObjectPropertyDifference,
    getEmbeddedProps,
    StateChangeManager,
} from "@html_editor/others/embedded_component_utils";
import { Component, onMounted, onWillDestroy, proxy, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";

export class EmbeddedCaptionComponent extends Component {
    static template = "html_editor.EmbeddedCaption";

    static props = {
        image: t.instanceOf(Element),
        onUpdateCaption: t.function(),
        onEditorHistoryApply: t.function(),
        focusInput: t.boolean(),
        host: t.object(),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.state = proxy({
            caption: this.props.image.getAttribute("data-caption") || "",
            host: this.props.host,
        });
        this.captionInput = elementRef();
        if (this.props.focusInput) {
            onMounted(() => {
                this.captionInput.el.focus();
            });
        }
        this._appliedNativeHistory = true;
        this.updateCaption();
        const observer = new MutationObserver((mutations) => {
            for (const mutation of mutations) {
                if (
                    mutation.type === "attributes" &&
                    mutation.attributeName === "data-caption"
                ) {
                    const incomingValue = mutation.target.getAttribute("data-caption");
                    if (incomingValue !== this.state.caption) {
                        this.updateCaption();
                    }
                }
            }
        });
        observer.observe(this.props.image, { attributes: true });
        onWillDestroy(() => {
            observer.disconnect();
        });
    }

    updateCaption(caption = this.props.image.getAttribute("data-caption")) {
        this.state.caption = caption;
        this.props.onUpdateCaption(caption);
    }

    onInputBlur() {
        setTimeout(() => {
            if (this.captionInput.el) {
                this.updateCaption(this.captionInput.el.value || "");
            }
        });
    }

    onInputKeyup(ev) {
        if (ev.key === "z" && ev.ctrlKey && !this._appliedNativeHistory) {
            this.props.onEditorHistoryApply(ev.shiftKey);
        }
        this._appliedNativeHistory = false;
    }

    onInputBeforeInput(ev) {
        this._appliedNativeHistory = false;
        if (ev.inputType === "historyUndo" || ev.inputType === "historyRedo") {
            this._appliedNativeHistory = true;
        }
    }
}

export const captionEmbedding = {
    name: "caption",
    Component: EmbeddedCaptionComponent,
    getProps: (host) => ({ host, ...getEmbeddedProps(host) }),
    getStateChangeManager: (config) =>
        new StateChangeManager(
            Object.assign(config, {
                propertyUpdater: {
                    caption: (state, previous, next) => {
                        applyObjectPropertyDifference(
                            state,
                            "caption",
                            previous.caption,
                            next.caption,
                        );
                    },
                },
            }),
        ),
};
