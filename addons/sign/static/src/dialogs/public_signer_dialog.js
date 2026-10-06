/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { isEmail } from "@web/core/utils/format/strings";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";

export class PublicSignerDialog extends Component {
    static template = "sign.PublicSignerDialog";
    static components = {
        Dialog,
    };
    static props = {
        name: t.string(),
        mail: t.string(),
        postValidation: t.function(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        this.nameInput = elementRef();
        this.mailInput = elementRef();
        this.signInfo = useService("signInfo");
    }

    get dialogProps() {
        return {
            title: _t("Final Validation"),
            size: "md",
            technical: this.ui.isSmall,
            fullscreen: this.ui.isSmall,
        };
    }

    async submit() {
        const name = this.nameInput.el.value;
        const mail = this.mailInput.el.value;
        if (!this.validateForm(name, mail)) {
            return false;
        }

        const response = await rpc(
            `/sign/send_public/${this.signInfo.get("documentId")}/${this.signInfo.get(
                "signRequestToken",
            )}`,
            { name, mail },
        );

        await this.props.postValidation(
            response["requestID"],
            response["requestToken"],
            response["accessToken"],
        );
        this.props.close();
    }

    validateForm(name, mail) {
        const isEmailInvalid = !mail || !isEmail(mail);
        if (!name || isEmailInvalid) {
            this.nameInput.el.classList.toggle("is-invalid", !name);
            this.mailInput.el.classList.toggle("is-invalid", isEmailInvalid);
            return false;
        }
        return true;
    }
}
