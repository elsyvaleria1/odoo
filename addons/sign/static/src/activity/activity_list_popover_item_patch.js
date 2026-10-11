/** @odoo-module native */
import { ActivityListPopoverItem } from "@mail/core/web/activity_list_popover_item";
import { user } from "@web/core/user";
import { patch } from "@web/core/utils/patch";

import { signFromActivity } from "./sign_from_activity_hook.js";

patch(ActivityListPopoverItem.prototype, {
    setup() {
        super.setup();
        this.user = user.userId;
        const functions = signFromActivity();
        Object.assign(this, functions);
    },

    get hasMarkDoneButton() {
        return (
            super.hasMarkDoneButton &&
            this.props.activity.activity_category !== "sign_request"
        );
    },

    async onClickRequestSign() {
        const { res_model, res_id } = this.props.activity;
        if (res_model === "sign.request") {
            const result = await this.openSignRequestAction(res_id);
            if (result) {
                return;
            }
        }
        const documentReference =
            res_model && res_model !== "sign.request" && res_id
                ? `${res_model},${res_id}`
                : false;
        await this.props.activity.requestSignature(
            this.props.onActivityChanged,
            documentReference,
            res_model,
            res_id,
        );
    },
});
