/** @odoo-module native */
import { DiscussChannel } from "@mail/discuss/core/common/discuss_channel_model";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

patch(DiscussChannel.prototype, {
    get composerPlaceholder() {
        if (this.channel_type === "email") {
            return _t("Email %(correspondent)s… (Ctrl+Enter sends)", {
                correspondent: this.displayName,
            });
        }
        return super.composerPlaceholder;
    },
});
