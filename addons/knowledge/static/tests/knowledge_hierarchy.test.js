import KnowledgeHierarchy from "@knowledge/components/hierarchy/hierarchy";
import { useKnowledgeContext } from "@knowledge/js/knowledge_context";
import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { after, before, expect, test } from "@odoo/hoot";
import { click, queryFirst } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { Component, useProps, xml } from "@odoo/owl";
import {
    defineModels,
    fields,
    MockServer,
    models,
    mountView,
    onRpc,
} from "@web/../tests/web_test_helpers";
import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets";

class Article extends models.Model {
    name = fields.Char();
    icon = fields.Char();
    display_name = fields.Char();
    parent_id = fields.Many2one({ relation: "article" });
    root_article_id = fields.Many2one({ relation: "article" });
    parent_path = fields.Char();
    is_locked = fields.Boolean();
    user_can_write = fields.Boolean();
    user_has_access = fields.Boolean();
    category = fields.Char();

    _records = [
        {
            id: 1,
            name: "Root Article",
            icon: "🙂",
            display_name: "🙂 Root Article",
            parent_id: false,
            root_article_id: 1,
            parent_path: "1/",
            is_locked: false,
            user_can_write: true,
            user_has_access: true,
            category: "workspace",
        },
        {
            id: 2,
            name: "Article 2",
            icon: "🙃",
            display_name: "🙃 Article 2",
            parent_id: 1,
            root_article_id: 1,
            parent_path: "1/2/",
            is_locked: false,
            user_can_write: true,
            user_has_access: true,
            category: "workspace",
        },
        {
            id: 3,
            name: "Article 3",
            icon: false,
            display_name: "Article 3",
            parent_id: 2,
            root_article_id: 1,
            parent_path: "1/2/3/",
            is_locked: false,
            user_can_write: true,
            user_has_access: true,
            category: "workspace",
        },
        {
            id: 4,
            name: "Article 4",
            icon: "😎",
            display_name: "😎 Article 4",
            parent_id: 3,
            root_article_id: 1,
            parent_path: "1/2/3/4/",
            is_locked: false,
            user_can_write: true,
            user_has_access: true,
            category: "workspace",
        },
        {
            id: 5,
            name: "Article 5",
            icon: false,
            display_name: "Article 5",
            parent_id: false,
            root_article_id: 5,
            parent_path: "5/",
            is_locked: false,
            user_can_write: true,
            user_has_access: true,
            category: "workspace",
        },
    ];
}

defineMailModels();
defineModels([Article]);

onRpc("get_sidebar_articles", function () {
    return {
        articles: this.env["article"]._filter(),
        favorite_ids: [],
    };
});

onRpc(
    "get_article_hierarchy",
    async function ({
        args: [articleId],
        kwargs: { exclude_article_ids: excludeArticleIds },
    }) {
        const Article = this.env["article"];
        return Article.slice(
            0,
            Article.indexOf(Article.browse(articleId)[0]) - 1,
        ).filter((article) => !excludeArticleIds.includes(article.id));
    },
);

onRpc("has_access", function () {
    return true;
});

let openArticle;

before(() => {
    class KnowledgeNavigation extends Component {
        static template = xml`
            <KnowledgeHierarchy record="this.props.record"/>
        `;
        static components = {
            KnowledgeHierarchy,
        };
        static props = { ...standardWidgetProps };
        props = useProps(this.constructor.props);
        setup() {
            const knowledgeContext = useKnowledgeContext();
            openArticle = (resId) => knowledgeContext.openArticle(resId);
        }
    }
    registry.category("view_widgets").add("knowledge_navigation", {
        component: KnowledgeNavigation,
        fieldDependencies: Object.entries(Article._fields).map(
            ([fieldName, field]) => ({
                name: fieldName,
                type: field.type,
            }),
        ),
    });
});
after(() => registry.category("view_widgets").remove("knowledge_navigation"));

/** @param {number} articleId */
const assertCurrentArticle = (articleId) => {
    const [article] = MockServer.env["article"].browse(articleId);
    expect(`.o_article_active:contains(${article.name})`).toHaveCount(1);
};

/** @param {array} articleIds */
const assertHierarchyArticles = async (articleIds) => {
    expect(".o_hierarchy_item").toHaveCount(articleIds.length);
    if (articleIds.length > 3) {
        await openHierarchyDropdown();
    }
    MockServer.env["article"].browse(articleIds).forEach((article, idx) => {
        if (idx === articleIds.length - 1) {
            expect(
                `.o_hierarchy_item:last-of-type:contains(${article.icon || "📄"})`,
            ).toHaveCount(1);
            if (article.is_locked || !article.user_can_write) {
                expect(
                    `.o_hierarchy_item:last-of-type:contains(${article.name})`,
                ).toHaveCount(1);
            } else {
                expect(
                    `.o_hierarchy_item:last-of-type input:value(${article.name})`,
                ).toHaveCount(1);
            }
        } else if (idx < articleIds.length - 2 && idx > 0) {
            expect(
                `.o-dropdown-item:nth-of-type(${idx}):contains(${article.display_name})`,
            ).toHaveCount(1);
        } else {
            expect(
                `.o_hierarchy_item:nth-of-type(${idx + 1}) a:contains(${article.display_name})`,
            ).toHaveCount(1);
        }
    });
};

/** @param {number} id */
const clickHierarchyArticle = async (articleId) => {
    const [article] = MockServer.env["article"].browse(articleId);
    const articleName = article.name;
    const articleElement = queryFirst(`.o_hierarchy_item:contains(${articleName})`);
    if (articleElement) {
        await click(articleElement.querySelector("a"));
    } else {
        await openHierarchyDropdown();
        await click(`.o-dropdown-item:contains(${articleName})`);
    }
    return animationFrame();
};

const openHierarchyDropdown = async () => {
    if (queryFirst(".o_hierarchy_item a:contains('...').show")) {
        return;
    }
    await click(".o_hierarchy_item a:contains('...')");
    return animationFrame();
};

const viewParams = {
    arch: `
        <form js_class="knowledge_article_view_form">
            <widget name="knowledge_navigation" class="d-flex"/>
        </form>
    `,
    resModel: "article",
    type: "form",
};

test("Hierarchy - Open articles in hierarchy", async function () {
    await mountView({ ...viewParams, resId: 4 });
    await assertHierarchyArticles([1, 2, 3, 4]);
    await clickHierarchyArticle(3);
    await assertHierarchyArticles([1, 2, 3]);
    await clickHierarchyArticle(2);
    await assertHierarchyArticles([1, 2]);
    await clickHierarchyArticle(1);
    await assertHierarchyArticles([1]);
    openArticle(4);
    await animationFrame();
    await assertHierarchyArticles([1, 2, 3, 4]);
    await clickHierarchyArticle(2);
    assertCurrentArticle(2);
});

test("Hierarchy - Inaccessible articles", async function () {
    Article._records[1].user_has_access = false;
    Article._records[3].user_can_write = false;
    await mountView({ ...viewParams, resId: 4 });
    await assertHierarchyArticles([1, 2, 3, 4]);
    expect(".o_hierarchy_item a.o_article_emoji").toHaveCount(0);
    expect(".o_hierarchy_item input").toHaveCount(0);
    const [article] = MockServer.env["article"].browse(2);
    expect(`.o-dropdown-item.disabled:contains(${article.display_name})`).toHaveCount(
        1,
    );
});
