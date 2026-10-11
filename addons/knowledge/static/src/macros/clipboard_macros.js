/** @odoo-module native */
import { AbstractMacro } from "@knowledge/macros/abstract_macro";
import { pasteElements, replaceHtmlFieldContentWith } from "@knowledge/macros/utils";

export class SendAsMessageMacro extends AbstractMacro {
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
            },
            {
                trigger: () => {
                    this.validatePage();
                    return this.getFirstVisibleElement(
                        '.o-mail-Composer button[name="open-full-composer"]:not([disabled])',
                    );
                },
                async action(trigger) {
                    trigger.click();
                },
            },
            {
                trigger: () => {
                    this.validatePage();
                    const dialog = this.getFirstVisibleElement(
                        ".o_dialog .o_mail_composer_form",
                    );
                    if (dialog) {
                        return this.getFirstVisibleElement(
                            dialog.querySelector(
                                '.o_field_html[name="body"] .odoo-editor-editable',
                            ),
                        );
                    }
                    return null;
                },
                action: (el) => {
                    replaceHtmlFieldContentWith(this.data.dataTransfer, el);
                },
            },
            {
                action: () => this.unblockUI(),
            },
        ];
    }
}

export class UseAsDescriptionMacro extends AbstractMacro {
    /**
     * @override
     * @returns {Array[Object]}
     */
    getSteps() {
        return [
            {
                trigger: () => this.getFirstVisibleElement(".o_form_editable"),
            },
            {
                trigger: () => {
                    this.validatePage();
                    const el = this.getFirstVisibleElement(
                        `.o_field_html[name="${this.data.fieldName}"]`,
                        (element) => element.querySelector(".odoo-editor-editable"),
                    );
                    if (el) {
                        return el;
                    }
                    if (this.data.pageName) {
                        this.searchInXmlDocNotebookTab(
                            `page[name="${this.data.pageName}"]`,
                        );
                    }
                    return null;
                },
                async action(trigger) {
                    trigger.click();
                },
            },
            {
                trigger: () => {
                    this.validatePage();
                    return this.getFirstVisibleElement(
                        `.o_field_html[name="${this.data.fieldName}"] .odoo-editor-editable`,
                    );
                },
                action: (el) => {
                    el.addEventListener(
                        "onHistoryResetFromPeer",
                        () => pasteElements(this.data.dataTransfer, el),
                        { once: true },
                    );
                    pasteElements(this.data.dataTransfer, el);
                },
            },
            {
                action: () => this.unblockUI(),
            },
        ];
    }
}
