/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { AlertDialog, Dialog } from "@web/ui/dialog";

export class SMSSignerDialog extends Component {
    static template = "sign.SMSSignerDialog";
    static components = {
        Dialog,
    };
    static props = {
        signerPhone: t.string().optional(),
        postValidation: t.function(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        this.validationCodeInput = elementRef();
        this.phoneInput = elementRef();
        this.dialog = useService("dialog");
        this.signInfo = useService("signInfo");
        this.SMSInfo = { phoneNumber: this.props.signerPhone || "" };
        this.state = proxy({
            sendingSMS: false,
            SMSCount: 0,
        });

        useLayoutEffect(
            () => () => {
                browser.clearTimeout(this.timeout);
            },
            () => [],
        );
    }

    sendSMS(phoneNumber) {
        this.state.sendingSMS = true;
        const route = `/sign/send-sms/${this.signInfo.get("documentId")}/${this.signInfo.get(
            "signRequestItemToken",
        )}/${encodeURIComponent(phoneNumber)}`;
        rpc(route)
            .then((success) => {
                if (success) {
                    this.handleSendSMSSuccess();
                } else {
                    this.handleSMSError();
                }
            })
            .catch((_) => {
                this.handleSMSError();
            });
    }

    handleSendSMSSuccess() {
        this.timeout = browser.setTimeout(() => {
            this.state.sendingSMS = false;
            this.state.SMSCount++;
        }, 15000);
    }

    handleSMSError() {
        this.state.sendingSMS = false;
        this.dialog.add(AlertDialog, {
            title: _t("Error"),
            body: _t(
                "Unable to send the SMS. If you just requested codes, wait a few minutes; otherwise contact the sender of the document.",
            ),
        });
    }

    onSendSMSClick(e) {
        const sendButton = e.target;
        sendButton.setAttribute("disabled", true);
        const phoneNumber = this.phoneInput.el.value;
        if (phoneNumber) {
            this.SMSInfo.phoneNumber = phoneNumber;
            this.sendSMS(phoneNumber);
        }
        sendButton.removeAttribute("disabled");
    }

    async validateSMS(e) {
        const validateButton = e.target;
        const validationCode = this.validationCodeInput.el?.value;
        if (!validationCode) {
            this.validationCodeInput.el.classList.toggle("is-invalid");
            return false;
        }
        validateButton.setAttribute("disabled", true);
        await this.props.postValidation(validationCode);
        validateButton.removeAttribute("disabled");
        this.props.close();
    }

    get dialogProps() {
        return {
            size: "md",
            title: _t("Final Validation"),
            fullscreen: this.ui.isSmall,
        };
    }
}
