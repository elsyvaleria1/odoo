/** @odoo-module native */
import { ComposerAction } from "@mail/core/common/composer_actions";
import { portalContextOf } from "@portal/chatter/core/portal_context";
import { patch } from "@web/core/utils/patch";

patch(ComposerAction.prototype, {
    _condition({ owner }) {
        if (
            this.id === "open-full-composer" &&
            portalContextOf(owner).projectSharingId
        ) {
            return false;
        }
        return super._condition(...arguments);
    },
});
