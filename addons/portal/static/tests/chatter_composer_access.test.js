import {
    contains,
    defineMailModels,
    start,
    startServer,
} from "@mail/../tests/mail_test_helpers";
import { Chatter } from "@mail/chatter/web_portal/chatter";
import { after, describe, getFixture, test } from "@odoo/hoot";
import { App, Component, useProps, xml } from "@odoo/owl";
import { PortalChatterService } from "@portal/chatter/frontend/portal_chatter_service";
import { getService, onRpc, patchWithCleanup } from "@web/../tests/web_test_helpers";
import { Deferred } from "@web/core/utils/concurrency";

describe.current.tags("desktop");
defineMailModels();

class Page extends Component {
    static props = {};
    static template = xml`<div/>`;
    props = useProps(this.constructor.props);
}

async function mountPortalChatter({ canPost }) {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Shared Record" });
    onRpc("/portal/chatter_init", () => ({
        "mixin.mail.thread": [
            { id: partnerId, model: "res.partner", can_post: canPost },
        ],
    }));
    patchWithCleanup(odoo, { portalChatterReady: new Deferred() });
    const env = await start({ root: Page });
    const apps = [];
    patchWithCleanup(App.prototype, {
        createRoot() {
            apps.push(this);
            return super.createRoot(...arguments);
        },
    });
    after(() => apps.forEach((app) => app.destroy()));
    getFixture().insertAdjacentHTML(
        "beforeend",
        `<div class="o_portal_chatter" data-res_id="${partnerId}" data-res_model="res.partner" data-allow_composer="1" data-token="a-link-token"></div>`,
    );
    const service = new PortalChatterService(env, {
        "mail.store": getService("mail.store"),
    });
    patchWithCleanup(service, { createShadow: async (root) => root });
    // the backend extensions of mail.Chatter in this bundle are not the portal's
    patchWithCleanup(Chatter, {
        template: xml`<div class="o-mail-Chatter"><div t-if="this.props.composer" class="o-mail-Composer"/></div>`,
    });
    patchWithCleanup(Chatter.prototype, { _onMounted() {}, load() {} });
    await service.initialize(env);
}

test("a credential that may not post gets no composer", async () => {
    await mountPortalChatter({ canPost: false });
    await contains(".o-mail-Chatter");
    await contains(".o-mail-Composer", { count: 0 });
});

test("a credential that may post gets the composer", async () => {
    await mountPortalChatter({ canPost: true });
    await contains(".o-mail-Chatter .o-mail-Composer");
});
