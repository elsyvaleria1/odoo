/** @odoo-module native */
import { activityGroupOpener } from "@mail/core/web/activity_group_opener";
import { ActivityMenu } from "@mail/core/web/activity_menu";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

patch(ActivityMenu.prototype, {
    setup() {
        super.setup();
        this.documentService = useService("document.document");
    },

    onClickRequestDocument() {
        this.dropdown.close();
        this.action.doAction("document.action_request_form");
    },
});

// the systray and the home activities tile open documents in the Documents app
patch(activityGroupOpener, {
    async execute(context, group, domain, views, actionContext, newWindow) {
        if (group.model !== "document.document") {
            return super.execute(...arguments);
        }
        const { action } = context.services;
        const loaded = await action.loadAction("document.document_action");
        loaded.domain = domain;
        return action.doAction(loaded, {
            newWindow,
            clearBreadcrumbs: true,
            viewType: group.view_type,
            additionalContext: actionContext,
        });
    },
});
