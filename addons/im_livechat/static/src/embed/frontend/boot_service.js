/** @odoo-module native */
import { makeRoot, makeShadow } from "@im_livechat/embed/common/boot_helpers";
import { canLoadLivechat } from "@im_livechat/embed/common/misc";
import { LivechatRoot } from "@im_livechat/embed/frontend/livechat_root";
import { App } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { makeAppConfig } from "@web/env";

export const livechatBootService = {
    dependencies: ["mail.store"],

    getTarget() {
        return document.body;
    },

    start(env) {
        if (!canLoadLivechat()) {
            return;
        }
        const target = this.getTarget();
        const root = makeRoot(target);
        makeShadow(root).then((shadow) => {
            env.services["discuss.rtc"].rootEl = shadow;
            new App(makeAppConfig(env, { name: "LivechatRoot" }))
                .createRoot(LivechatRoot)
                .mount(shadow);
        });
    },
};
registry.category("services").add("im_livechat.boot", livechatBootService);
