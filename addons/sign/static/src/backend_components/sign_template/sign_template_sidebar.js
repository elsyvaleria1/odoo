/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { useSignViewButtons } from "@sign/views/hooks";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { getDataURLFromFile } from "@web/core/utils/urls";

import { SignTemplateSidebarRoleItems } from "./sign_template_sidebar_role_items.js";

export class SignTemplateSidebar extends Component {
    static template = "sign.SignTemplateSidebar";
    static components = {
        SignTemplateSidebarRoleItems,
        Dropdown,
        DropdownItem,
    };
    static props = {
        signItemTypes: t.array(),
        isSignRequest: t.boolean(),
        signTemplateId: t.number(),
        updateRoleName: t.function(),
        signers: t.array(),
        hasSignRequests: t.boolean(),
        updateDocumentName: t.function(),
        updateSigners: t.function(),
        pushNewSigner: t.function(),
        updateCollapse: t.function(),
        deleteRole: t.function(),
        documents: t.array(),
        selectedDocumentId: t.number(),
        updateSelectedDocument: t.function(),
        updateDocuments: t.function(),
        deleteDocument: t.function(),
        moveDocumentUp: t.function(),
        moveDocumentDown: t.function(),
        onEditTemplate: t.function(),
        onUpdateDocument: t.function(),
        saveManually: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        this.action = useService("action");
        this.orm = useService("orm");
        this.state = proxy({
            editableDocumentId: false,
        });
        this.uploadFileInputRef = elementRef();
        const functions = useSignViewButtons(this, this.uploadFileInputRef);
        Object.assign(this, functions);
    }

    focusOnNewAddedSigner(roleId) {
        const spanSelector = `span[data-role-id="${roleId}"]`;
        const inputSelector = `input[data-role-id="${roleId}"]`;

        // Polling function to check if the input is available in the DOM
        const checkInput = () => {
            const span = document.querySelector(spanSelector);
            const input = document.querySelector(inputSelector);

            // If the span and input are found, focus on input
            if (span && input) {
                span.click();
                input.focus();
                input.select();
            } else {
                // If input is not found, wait for the next frame and check again
                requestAnimationFrame(checkInput);
            }
        };

        checkInput();
    }

    async onClickAddSigner() {
        await this.props.pushNewSigner();
        this.focusOnNewAddedSigner(this.props.signers.at(-1).roleId);
    }

    deleteSigner(signerId, roleId) {
        const updatedSigners = [...this.props.signers].filter(
            (signer) => signer.id !== signerId,
        );

        /* After deleting the signer, if no signer is focused, focus the last one in the array. */
        if (
            !updatedSigners.some((signer) => !signer.isCollapsed) &&
            updatedSigners.length > 0
        ) {
            updatedSigners[updatedSigners.length - 1].isCollapsed = false;
        }

        this.props.updateSigners(updatedSigners);
        this.props.deleteRole(roleId);
    }

    // TODO: remove in master
    updateSignerNames(signers) {
        let signer_idx = 1;
        const str = _t("Signer");
        for (const signer of signers) {
            if (signer.name.includes(str)) {
                signer.name = _t("Signer %s", signer_idx);
                this.props.updateRoleName(signer.roleId, signer.name);
            }
            signer_idx++;
        }
    }

    getSidebarRoleItemsProps(id) {
        //  TODO MASTER: we should put the role name here. it would prevent one rpc per role...
        const signer = this.props.signers.find((signer) => signer.id === id);
        return {
            id: id,
            name: signer.name,
            signTemplateId: this.props.signTemplateId,
            roleId: signer.roleId,
            colorId: signer.colorId,
            signItemTypes: this.props.signItemTypes,
            isSignRequest: this.props.isSignRequest,
            updateRoleName: this.props.updateRoleName,
            isCollapsed: signer.isCollapsed,
            isInputFocused: signer.isInputFocused,
            /* Update callbacks binding for parent props: */
            updateCollapse: (id, value) => this.props.updateCollapse(id, value),
            onDelete: () => this.deleteSigner(id, signer.roleId),
            onFieldNameInputKeyUp: (ev) => this.onFieldNameInputKeyUp(ev),
            itemsCount: signer.itemsCount,
            hasSignRequests: this.props.hasSignRequests,
            assignTo: signer.assignTo,
        };
    }

    onDocumentNameBlur() {
        this.state.editableDocumentId = false;
    }

    onFieldNameInputKeyUp(ev) {
        if (ev.key === "Enter") {
            ev.target.blur();
        }
    }

    onUpdateSelectedDocument(documentId) {
        this.props.updateSelectedDocument(documentId);
    }

    onDocumentNameChanged(documentId, e) {
        const documentName = e.target.value;
        if (documentName) {
            this.props.updateDocumentName(documentId, documentName);
        }
    }

    setEditableDocumentId(documentId) {
        this.state.editableDocumentId = documentId;
        this.props.updateSelectedDocument(documentId);
    }

    onDocumentNameTextClick(documentId) {
        this.state.editableDocumentId = documentId;
        const input = document.querySelector(`[data-document-id="${documentId}"]`);

        // Polling function to check if the input is no longer `d-none`
        const waitForVisibility = () => {
            if (input && !input.classList.contains("d-none")) {
                // Input is visible, so we can focus
                input.focus();
                input.select();
            } else {
                // Input is still hidden, keep checking in the next frame
                requestAnimationFrame(waitForVisibility);
            }
        };

        waitForVisibility();
    }

    async onRemoveDocument(documentId) {
        await this.props.deleteDocument(documentId);
    }

    async onMoveDocumentUp(documentId) {
        await this.props.moveDocumentUp(documentId);
    }

    async onMoveDocumentDown(documentId) {
        await this.props.moveDocumentDown(documentId);
    }

    async onUpdateDocument(documentId, ev) {
        /* Check if pdf got uploaded, save manually, and call update document function from props. */
        const file = ev.target.files && ev.target.files.length && ev.target.files[0];
        if (!file) {
            return;
        }
        if (this.props.saveManually) {
            await this.props.saveManually();
        }
        const url = await getDataURLFromFile(file);
        const fileData = {
            name: file.name,
            datas: url.split(",")[1],
        };
        await this.props.onUpdateDocument(documentId, fileData);
    }
}
