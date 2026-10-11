/** @odoo-module native */
import { whenReady } from "@odoo/owl";
import { loadLocalization } from "@web/core/l10n/localization_service";
import { makeEnv, mountComponent } from "@web/env";

import { EmailSharingInput } from "./public/components/slide_share_dialog/email_sharing_input.js";

whenReady(async () => {
    const target = document.querySelector(".o_wslides_embed_share_email");
    if (!target) {
        return;
    }
    await loadLocalization();
    await mountComponent(EmailSharingInput, target, {
        env: makeEnv(),
        props: {
            id: Number(target.dataset.slideId),
            category: target.dataset.category,
        },
    });
});
