/** @odoo-module native */
import { useDocModelStore } from "@api_doc/doc_model_store_context";
import { Component, useListener, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useMountedListener } from "@web/core/utils/hooks";

export class ApiKeyModal extends Component {
    static template = "api_doc.DocApiKeyModal";

    static components = {};
    static props = {};
    props = useProps(this.constructor.props);

    setup() {
        this.docContext = useDocModelStore();
        this.modalRef = elementRef();

        useListener(window, "keydown", (event) => {
            if (event.key === "Escape") {
                this.cancel();
            }
        });

        useMountedListener(window, "click", (event) => {
            if (!this.modalRef.el.contains(event.target)) {
                this.cancel();
            }
        });
    }

    save() {
        this.docContext.modelStore.setAPIKey(
            this.modalRef.el.querySelector(":scope input").value.trim(),
        );
        this.docContext.modelStore.showApiKeyModal = false;
    }

    cancel() {
        this.docContext.modelStore.showApiKeyModal = false;
    }

    async openAPIKeyForm() {
        window.open(
            `${window.location.origin}/odoo/action-doc_api_key_wizard`,
            "_blank",
        );
    }
}
