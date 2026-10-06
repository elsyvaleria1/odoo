/** @odoo-module native */
import { proxy } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useEventBus } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

export const SignDocumentDropZone = (T) =>
    class SignDocumentDropZone extends T {
        setup() {
            super.setup();
            this.bus = useEventBus();
            this.root = elementRef();
            this.dragState = proxy({
                showDragZone: false,
            });
            useLayoutEffect(
                (el) => {
                    if (!el) {
                        return;
                    }
                    const highlight = this.highlight.bind(this);
                    const unhighlight = this.unhighlight.bind(this);
                    const drop = this.onDrop.bind(this);
                    el.addEventListener("dragover", highlight);
                    el.addEventListener("dragleave", unhighlight);
                    el.addEventListener("drop", drop);
                    return () => {
                        el.removeEventListener("dragover", highlight);
                        el.removeEventListener("dragleave", unhighlight);
                        el.removeEventListener("drop", drop);
                    };
                },
                () => [document.querySelector(".o_content")],
            );
        }

        highlight(ev) {
            ev.stopPropagation();
            ev.preventDefault();
            this.dragState.showDragZone = true;
        }

        unhighlight(ev) {
            ev.stopPropagation();
            ev.preventDefault();
            this.dragState.showDragZone = false;
        }

        async onDrop(ev) {
            ev.preventDefault();
            const files = ev.dataTransfer.files;
            const resModel = this.props.list.config.resModel;
            if (files.length) {
                await this.bus.trigger("change_file_input", { files, resModel });
            }
            this.dragState.showDragZone = false;
        }
    };
