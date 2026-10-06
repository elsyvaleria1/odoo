/** @odoo-module native */
import { Composer } from "@mail/core/common/composer_model";
import { patch } from "@web/core/utils/patch";

patch(Composer.prototype, {
    get syncHtmlWithMessage() {
        return super.syncHtmlWithMessage && !this.portalComment;
    },
});
