/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";

export class NextDirectSignDialog extends Component {
    static template = "sign.NextDirectSignDialog";
    static components = {
        Dialog,
    };
    static props = { close: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        this.action = useService("action");
        this.signInfo = useService("signInfo");
        this.title = _t("Thank You!");
    }

    goToNextSigner() {
        const newCurrentToken = this.signInfo.get("tokenList").shift();
        this.signInfo.get("nameList").shift();
        this.action.doAction(
            {
                type: "ir.actions.client",
                tag: "sign.SignableDocument",
                name: _t("Sign"),
            },
            {
                additionalContext: {
                    id: this.signInfo.get("documentId"),
                    create_uid: this.signInfo.get("createUid"),
                    state: this.signInfo.get("signRequestState"),
                    token: newCurrentToken,
                    token_list: this.signInfo.get("tokenList"),
                    name_list: this.signInfo.get("nameList"),
                },
                stackPosition: "replaceCurrentAction",
            },
        );
        this.props.close();
    }

    get nextSigner() {
        return this.signInfo.get("nameList")[0];
    }

    get dialogProps() {
        return {
            size: "md",
            technical: this.ui.isSmall,
            fullscreen: this.ui.isSmall,
        };
    }
}
