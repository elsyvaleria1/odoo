/** @odoo-module native */
import { Component, markup, onMounted, onWillUnmount, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { htmlJoin } from "@web/core/utils/dom/html";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/fields/standard_field_props";

export class MailComposerChatGPT extends Component {
    static template = "mail.MailComposerChatGPT";
    static props = { ...standardFieldProps };
    props = useProps(this.constructor.props);

    setup() {
        this.store = useService("mail.store");
        this.orm = useService("orm");
        this.aiChatLauncher = useService("aiChatLauncher");
        let currentDialog, previousZIndex;
        onMounted(() => {
            currentDialog = document.querySelector(".o-overlay-item:has(.o_dialog");
            if (currentDialog) {
                previousZIndex = currentDialog.style.zIndex;
                // 1020 is $zindex-sticky, the z-index of `.o-mail-ChatWindow` (see
                // addons/mail/static/src/core/common/chat_window.scss): matching it keeps the
                // dialog hosting this component below the chat windows.
                currentDialog.style.zIndex = "1020";
            }
        });
        onWillUnmount(() => {
            this.store.aiInsertButtonTarget = false;
            if (currentDialog) {
                currentDialog.style.zIndex = previousZIndex;
            }
        });
    }

    get originalRecordModel() {
        return this.props.record.data.model;
    }

    get originalRecordId() {
        return Number(this.props.record.data.res_ids.slice(1, -1));
    }

    async onOpenChatGPTPromptDialogBtnClick() {
        await this.aiChatLauncher.launchAIChat({
            callerComponentName: "mail_composer",
            recordModel: this.originalRecordModel,
            recordId: this.originalRecordId,
            originalRecordData: this.props.record.data,
            aiSpecialActions: {
                insert: (content) => {
                    const root = document.createElement("div");
                    root.appendChild(content);
                    const { body } = this.props.record.data;
                    // markup: innerHTML is safe, `root` is built from an already sanitized body
                    this.props.record.update({
                        body: htmlJoin([markup(root.innerHTML), body]),
                    });
                },
            },
            channelTitle: this.props.record.data.subject,
            aiChatSourceId: this.props.record.id,
        });
    }
}

export const mailComposerChatGPT = {
    component: MailComposerChatGPT,
    fieldDependencies: [{ name: "body", type: "text" }],
};

registry.category("fields").add("mail_composer_chatgpt", mailComposerChatGPT);
