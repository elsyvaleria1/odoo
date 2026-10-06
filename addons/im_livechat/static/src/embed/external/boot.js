/** @odoo-module native */
import { makeRoot, makeShadow } from "@im_livechat/embed/common/boot_helpers";
import { canLoadLivechat } from "@im_livechat/embed/common/misc";
import { whenReady } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { makeEnv, mountComponent, setRootAppContext, startServices } from "@web/env";
import { session } from "@web/session";
import { MainComponentsContainer } from "@web/ui/main_components_container";

(async function boot() {
    if (!canLoadLivechat()) {
        return;
    }
    session.origin = session.livechatData.serverUrl;
    await whenReady();
    if (session.test_mode) {
        await loadBundle("im_livechat.assets_livechat_support_tours");
    }
    const env = makeEnv();
    await startServices(env);
    setRootAppContext(env);
    odoo.isReady = true;
    const target = await makeShadow(makeRoot(document.body));
    env.services["discuss.rtc"].rootEl = target;
    await mountComponent(MainComponentsContainer, target, { env });
})();
