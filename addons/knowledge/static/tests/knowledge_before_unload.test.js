import { KnowledgeArticleFormController } from "@knowledge/js/knowledge_controller";
import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { expect, test } from "@odoo/hoot";
import { animationFrame, Deferred, mockSendBeacon } from "@odoo/hoot-mock";
import {
    contains,
    defineModels,
    fields,
    isPromptRequested,
    makeMockServer,
    models,
    mountView,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";

class KnowledgeArticle extends models.ServerModel {
    _name = "knowledge.article";

    category = fields.Generic({ default: "private" });
    user_can_write = fields.Generic({ default: true });
    user_has_access = fields.Generic({ default: true });
    active = fields.Boolean({ default: true });
    is_locked = fields.Boolean({ default: false });
    _onChanges = { name() {} };

    get_sidebar_articles() {
        return { articles: this._filter(), favorite_ids: [] };
    }
}

defineMailModels();
defineModels([KnowledgeArticle]);

/**
 * @param {{ name: string }} values
 */
async function mountArticle(values) {
    const mockServer = await makeMockServer();
    const articleId = mockServer.env["knowledge.article"].create(values);
    onRpc("get_user_sorted_articles", () => []);
    onRpc("has_access", () => true);
    /** @type {{ controller?: any }} */
    const box = {};
    patchWithCleanup(KnowledgeArticleFormController.prototype, {
        setup() {
            super.setup(...arguments);
            box.controller = this;
        },
    });
    /** @type {Blob[]} */
    const blobs = [];
    mockSendBeacon((_route, blob) => {
        blobs.push(blob);
        return true;
    });
    await mountView({
        arch: /* xml */ `
            <form js_class="knowledge_article_view_form">
                <field name="name"/>
                <field name="active" invisible="1"/>
                <field name="is_locked" invisible="1"/>
                <field name="user_can_write" invisible="1"/>
            </form>
        `,
        resModel: "knowledge.article",
        resId: articleId,
        type: "form",
    });
    box.controller.model.useSendBeaconToSaveUrgently = true;
    return { controller: box.controller, blobs };
}

/**
 * @param {{ controller: any, blobs: Blob[] }} article
 */
async function closeTab({ controller, blobs }) {
    let beaconsSent = 0;
    const requested = await isPromptRequested(
        (ev) => controller.beforeUnload(ev),
        () => (beaconsSent = blobs.length),
    );
    const texts = await Promise.all(blobs.map((blob) => blob.text()));
    return {
        requested,
        beaconsSent,
        values: texts.map((text) => JSON.parse(text).params.args[1]),
    };
}

test.tags("desktop");
test("closing the tab sends a typed name without waiting on its onchange", async () => {
    const onchange = new Deferred();
    onRpc("knowledge.article", "onchange", () => onchange);
    const article = await mountArticle({ name: "Draft" });
    await contains(".o_field_widget[name=name] input").edit("Final", {
        confirm: false,
    });

    const { requested, beaconsSent, values } = await closeTab(article);
    onchange.resolve();
    await animationFrame();

    expect(beaconsSent).toBe(1);
    expect(values).toEqual([{ name: "Final" }]);
    expect(requested).toBe(false);
});

test.tags("desktop");
test("closing the tab on an untitled article names it from its title in the beacon", async () => {
    const onchange = new Deferred();
    onRpc("knowledge.article", "onchange", () => onchange);
    const article = await mountArticle({ name: false });
    patchWithCleanup(article.controller, { getHtmlTitle: () => "From the heading" });

    const { requested, beaconsSent, values } = await closeTab(article);
    onchange.resolve();
    await animationFrame();

    expect(beaconsSent).toBe(1);
    expect(values).toEqual([{ name: "From the heading" }]);
    expect(requested).toBe(false);
});

test.tags("desktop");
test("closing the tab on an untouched titled article sends nothing and lets it go", async () => {
    const article = await mountArticle({ name: "Kept" });

    const { requested, beaconsSent } = await closeTab(article);

    expect(beaconsSent).toBe(0);
    expect(requested).toBe(false);
});
