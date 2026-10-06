/** @odoo-module native */

import { Component, onWillStart, t, useProps } from "@odoo/owl";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/fields/standard_field_props";

/**
 * This Component serves as both a widget in sign_request form view (data fetch needed)
 * and as a normal component in the control panel (uses existing data from signInfo).
 */
export class SignRequestDocumentsDropdown extends Component {
    static template = "sign.SignRequestDocumentsDropdown";
    static components = {
        Dropdown,
        DropdownItem,
    };
    static props = {
        ...standardFieldProps,
        name: t.string().optional(),
        record: t.object().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.signInfo = useService("signInfo");
        this.orm = useService("orm");
        this.action = useService("action");
        onWillStart(async () => {
            // Check if we're in a view context where we need to fetch sign request data
            const { context, evalContext } = this.props.record || {};
            if (evalContext?.id || context?.active_id) {
                // if active_id is present, we're in the form view context where we need to fetch sign request data
                // because signInfo service is not initialized with the required data
                await this.fetchSignRequestData();
            }
            // Fetch the actual documents (original or completed)
            await this.fetchSignRequestDocuments();
        });
    }

    /**
     * Fetch sign request data from the database
     * In the form view context, the signInfo service doesn't have the required data (documentId,
     * access_token, state) so we need to fetch it from the record context.
     */
    async fetchSignRequestData() {
        const { context, evalContext } = this.props.record || {};
        const signRequestId = evalContext?.id || context?.active_id;
        if (signRequestId) {
            const signRequestData = await this.orm.read(
                "sign.request",
                [signRequestId],
                ["access_token", "state"],
            );
            if (signRequestData?.length) {
                // Initialize signInfo with the fetched data
                this.signInfo.set({
                    documentId: signRequestId,
                    signRequestToken: signRequestData[0].access_token,
                    signRequestState: signRequestData[0].state,
                });
            }
        }
    }

    /**
     * Fetch sign request documents (original or completed)
     */
    async fetchSignRequestDocuments() {
        const signRequestState = this.signInfo?.get("signRequestState");
        const documentId = this.signInfo?.get("documentId");
        const signRequestToken = this.signInfo?.get("signRequestToken");

        if (!signRequestState || !documentId || !signRequestToken) {
            return;
        }

        if (signRequestState === "signed") {
            // Fetch completed (signed) documents
            const { completed_documents } = await rpc(
                `/sign/get_completed_documents/${documentId}/${signRequestToken}`,
            );
            this.signInfo.set({ completed_documents });
        } else {
            // Fetch original (unsigned) documents
            const { original_documents } = await rpc(
                `/sign/get_original_documents/${documentId}/${signRequestToken}`,
            );
            this.signInfo.set({ original_documents });
        }
    }

    /**
     * @param {string} suffix
     * @returns {string}
     */
    downloadUrl(suffix) {
        return `/sign/download/${this.signInfo.get("documentId")}/${this.signInfo.get("signRequestToken")}/${suffix}`;
    }

    downloadDocument(url) {
        return this.action.doAction({
            type: "ir.actions.act_url",
            target: "download",
            url,
        });
    }
}

// Register this component as a field widget to use in the sign_request form view
registry.category("fields").add("sign_request_documents_dropdown", {
    component: SignRequestDocumentsDropdown,
});
