/** @odoo-module native */
import { AbstractMacro } from "@knowledge/macros/abstract_macro";
import { dragAndDrop } from "@knowledge/macros/utils";

export class UseAsAttachmentMacro extends AbstractMacro {
    /**
     * @override
     * @returns {Array[Object]}
     */
    getSteps() {
        let attachFilesLastClickedEl = null;
        return [
            {
                trigger: () => {
                    this.validatePage();
                    const el = this.getFirstVisibleElement(
                        ".o-mail-Chatter-attachFiles:not([disabled])",
                        (matchEl) => {
                            const attachmentsCountEl = matchEl.querySelector("sup");
                            return (
                                attachmentsCountEl &&
                                Number.parseInt(attachmentsCountEl.textContent) > 0
                            );
                        },
                    );
                    if (el) {
                        const attachmentBoxEl = this.getFirstVisibleElement(
                            ".o-mail-AttachmentBox .o-mail-AttachmentList",
                        );
                        if (attachmentBoxEl) {
                            return attachmentBoxEl;
                        } else if (el !== attachFilesLastClickedEl) {
                            el.click();
                            attachFilesLastClickedEl = el;
                        }
                    } else {
                        this.searchInXmlDocNotebookTab("chatter");
                    }
                    return null;
                },
                action: (el) => el.scrollIntoView(),
            },
            {
                action: () => this.unblockUI(),
            },
        ];
    }
}

export class AttachToMessageMacro extends AbstractMacro {
    /**
     * @override
     * @returns {Array[Object]}
     */
    getSteps() {
        let sendMessageLastClickedEl = null;
        return [
            {
                trigger: () => {
                    this.validatePage();
                    const el = this.getFirstVisibleElement(
                        ".o-mail-Chatter-sendMessage:not([disabled])",
                    );
                    if (el) {
                        if (el.classList.contains("active")) {
                            return el;
                        } else if (el !== sendMessageLastClickedEl) {
                            el.click();
                            sendMessageLastClickedEl = el;
                        }
                    } else {
                        this.searchInXmlDocNotebookTab("chatter");
                    }
                    return null;
                },
                action: (el) => {
                    el.scrollIntoView();
                },
            },
            {
                trigger: () => {
                    this.validatePage();
                    return this.getFirstVisibleElement(
                        `.o-mail-Composer button[name="upload-files"]:not([disabled])`,
                    );
                },
                action: dragAndDrop.bind(this, "dragenter", this.data.dataTransfer),
            },
            {
                trigger: () => {
                    this.validatePage();
                    return this.getFirstVisibleElement(".o-mail-Composer-dropzone");
                },
                action: dragAndDrop.bind(this, "drop", this.data.dataTransfer),
            },
            {
                action: () => this.unblockUI(),
            },
        ];
    }
}
