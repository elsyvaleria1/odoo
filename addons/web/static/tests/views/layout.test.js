// @ts-check

import { expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import { Component, markup, onWillStart, proxy, useProps, xml } from "@odoo/owl";
import {
    defineModels,
    fields,
    makeMockEnv,
    models,
    mountWithCleanup,
    mountWithSearch,
} from "@web/../tests/web_test_helpers";
import { provideSearchModel } from "@web/core/search_model_hooks";
import { useService } from "@web/core/utils/hooks";
import { provideChildViewConfig } from "@web/core/view_config_hooks";
import { Layout } from "@web/search/layout";
import { SearchModel } from "@web/search/search_model";
import { EmptyState } from "@web/views/empty_state/empty_state";
import { getDefaultConfig } from "@web/views/view";
import { ViewLayout } from "@web/views/view_components/view_layout";

class Foo extends models.Model {
    aaa = fields.Selection({
        selection: [
            ["a", "A"],
            ["b", "B"],
        ],
    });

    _records = [
        {
            aaa: "a",
        },
        {
            aaa: "b",
        },
    ];

    _views = {
        search: `
            <search>
                <searchpanel>
                    <field name="aaa"/>
                </searchpanel>
            </search>
        `,
    };
}
defineModels([Foo]);

test(`Simple rendering`, async () => {
    class ToyComponent extends Component {
        static props = null;
        static template = xml`
            <Layout className="'o_view_sample_data'" display="this.props.display">
                <div class="toy_content"/>
            </Layout>
        `;
        static components = { Layout };
        props = useProps(this.constructor.props);
    }

    await mountWithCleanup(ToyComponent, {
        env: await makeMockEnv({ config: {} }),
    });
    expect(`.o_view_sample_data`).toHaveCount(1);
    expect(`.o_control_panel`).toHaveCount(0);
    expect(`.o_component_with_search_panel`).toHaveCount(0);
    expect(`.o_search_panel`).toHaveCount(0);
    expect(`.o_content > .toy_content`).toHaveCount(1);
});

test(`Simple rendering: with search`, async () => {
    class ToyComponent extends Component {
        static props = null;
        static template = xml`
            <Layout display="this.props.display">
                <t t-set-slot="layout-actions">
                    <div class="toy_search_bar"/>
                </t>
                <div class="toy_content"/>
            </Layout>
        `;
        static components = { Layout };
        props = useProps(this.constructor.props);
    }

    await mountWithSearch(ToyComponent, {
        resModel: "foo",
        searchViewId: false,
    });
    expect(`.o_control_panel .o_control_panel_actions .toy_search_bar`).toHaveCount(1);
    expect(`.o_component_with_search_panel .o_search_panel`).toHaveCount(1);
    expect(`.o_cp_searchview`).toHaveCount(0);
    expect(`.o_content > .toy_content`).toHaveCount(1);
});

test(`Rendering with default ControlPanel and SearchPanel`, async () => {
    class ToyComponent extends Component {
        static props = null;
        static template = xml`
            <Layout className="'o_view_sample_data'" display="{ controlPanel: {}, searchPanel: true }">
                <div class="toy_content"/>
            </Layout>
        `;
        static components = { Layout };
        props = useProps(this.constructor.props);

        setup() {
            this.searchModel = new SearchModel(SearchModel.useSearchScope(), {
                orm: useService("orm"),
                view: useService("view"),
            });
            provideSearchModel(this.searchModel);
            onWillStart(async () => {
                await this.searchModel.load({ resModel: "foo", searchViewId: false });
            });
        }
    }

    await mountWithCleanup(ToyComponent, {
        env: await makeMockEnv({
            config: {
                breadcrumbs: getDefaultConfig().breadcrumbs,
            },
        }),
    });
    expect(`.o_search_panel`).toHaveCount(1);
    expect(`.o_control_panel`).toHaveCount(1);
    expect(`.o_breadcrumb`).toHaveCount(1);
    expect(`.o_component_with_search_panel`).toHaveCount(1);
    expect(`.o_content > .toy_content`).toHaveCount(1);
});

test(`Nested layouts`, async () => {
    class ToyC extends Component {
        static props = null;
        static template = xml`
            <Layout className="'toy_c'" display="this.display">
                <div class="toy_c_content"/>
            </Layout>
        `;
        static components = { Layout };
        props = useProps(this.constructor.props);

        get display() {
            return {
                controlPanel: false,
                searchPanel: true,
            };
        }
    }

    class SearchPanel extends Component {
        static props = null;
        static template = xml`<div class="o_toy_search_panel"/>`;
        props = useProps(this.constructor.props);
    }

    class ToyB extends Component {
        static props = null;
        static template = xml`
            <Layout className="'toy_b'" display="this.props.display">
                <t t-set-slot="layout-actions">
                    <div class="toy_b_breadcrumbs"/>
                </t>
                <ToyC/>
            </Layout>
        `;
        static components = { Layout, ToyC };
        props = useProps(this.constructor.props);
        setup() {
            provideChildViewConfig({
                ...getDefaultConfig(),
                SearchPanel,
            });
        }
    }

    class ToyA extends Component {
        static props = null;
        static template = xml`
            <Layout className="'toy_a'" display="this.props.display">
                <t t-set-slot="layout-actions">
                    <div class="toy_a_search"/>
                </t>
                <ToyB display="this.props.display"/>
            </Layout>
        `;
        static components = { Layout, ToyB };
        props = useProps(this.constructor.props);
    }

    await mountWithSearch(ToyA, {
        resModel: "foo",
        searchViewId: false,
    });
    expect(`.o_content.toy_a .o_content.toy_b .o_content.toy_c`).toHaveCount(1);
    expect(".o_control_panel").toHaveCount(2);
    expect(".o_content.o_component_with_search_panel").toHaveCount(3);
    expect(`.o_search_panel`).toHaveCount(1);
    expect(".o_toy_search_panel").toHaveCount(2);
    expect(`.toy_a_search`).toHaveCount(1);
    expect(`.toy_b_breadcrumbs`).toHaveCount(1);
    expect(`.toy_c_content`).toHaveCount(1);
});

test(`Custom control panel`, async () => {
    class ToyComponent extends Component {
        static props = null;
        static template = xml`
            <Layout display="this.props.display">
                <div class="o_toy_content"/>
            </Layout>
        `;
        static components = { Layout };
        props = useProps(this.constructor.props);
    }

    class ControlPanel extends Component {
        static props = null;
        static template = xml`<div class="o_toy_search_panel"/>`;
        props = useProps(this.constructor.props);
    }

    await mountWithSearch(
        ToyComponent,
        {
            resModel: "foo",
            searchViewId: false,
        },
        { ControlPanel },
    );
    expect(`.o_toy_content`).toHaveCount(1);
    expect(`.o_toy_search_panel`).toHaveCount(1);
    expect(`.o_control_panel`).toHaveCount(0);
});

test(`Custom search panel`, async () => {
    class ToyComponent extends Component {
        static props = null;
        static template = xml`
            <Layout display="this.props.display">
                <div class="o_toy_content"/>
            </Layout>
        `;
        static components = { Layout };
        props = useProps(this.constructor.props);
    }

    class SearchPanel extends Component {
        static props = null;
        static template = xml`<div class="o_toy_search_panel"/>`;
        props = useProps(this.constructor.props);
    }

    await mountWithSearch(
        ToyComponent,
        {
            resModel: "foo",
            searchViewId: false,
        },
        { SearchPanel },
    );
    expect(`.o_toy_content`).toHaveCount(1);
    expect(`.o_toy_search_panel`).toHaveCount(1);
    expect(`.o_search_panel`).toHaveCount(0);
});

test(`Simple rendering: with dynamically displayed search`, async () => {
    const state = proxy({ displayLayoutActions: true });

    class ToyComponent extends Component {
        static props = null;
        static template = xml`
            <Layout display="this.display">
                <t t-set-slot="layout-actions">
                    <div class="toy_search_bar"/>
                </t>
                <div class="toy_content"/>
            </Layout>
        `;
        static components = { Layout };
        props = useProps(this.constructor.props);

        setup() {
            this.state = proxy(state);
        }

        get display() {
            return {
                ...this.props.display,
                controlPanel: {
                    ...this.props.display.controlPanel,
                    layoutActions: this.state.displayLayoutActions,
                },
            };
        }
    }

    await mountWithSearch(ToyComponent, {
        resModel: "foo",
        searchViewId: false,
    });
    expect(`.o_control_panel .o_control_panel_actions .toy_search_bar`).toHaveCount(1);
    expect(`.o_component_with_search_panel .o_search_panel`).toHaveCount(1);
    expect(`.o_cp_searchview`).toHaveCount(0);
    expect(`.o_content > .toy_content`).toHaveCount(1);

    state.displayLayoutActions = false;
    await animationFrame();
    expect(`.o_control_panel .o_control_panel_actions .toy_search_bar`).toHaveCount(0);
    expect(`.o_component_with_search_panel .o_search_panel`).toHaveCount(1);
    expect(`.o_cp_searchview`).toHaveCount(0);
    expect(`.o_content > .toy_content`).toHaveCount(1);
});

test(`ViewLayout: layout-actions-start renders before the search bar, layout-actions after it`, async () => {
    class ToyComponent extends Component {
        static props = null;
        static template = xml`
            <ViewLayout display="this.props.display">
                <t t-set-slot="layout-actions-start">
                    <div class="toy_before"/>
                </t>
                <t t-set-slot="layout-actions">
                    <div class="toy_after"/>
                </t>
                <div class="toy_content"/>
            </ViewLayout>
        `;
        static components = { ViewLayout };
        props = useProps(this.constructor.props);
    }

    await mountWithSearch(ToyComponent, {
        resModel: "foo",
        searchViewId: false,
    });
    expect(`.o_control_panel_actions .toy_before + .o_cp_searchview`).toHaveCount(1);
    expect(`.o_control_panel_actions .o_cp_searchview + .toy_after`).toHaveCount(1);
    expect(`.o_content > .toy_content`).toHaveCount(1);
});

test(`ViewLayout: a no-content slot replaces the EmptyState`, async () => {
    class ToyComponent extends Component {
        static props = null;
        static template = xml`
            <ViewLayout display="this.props.display" displayNoContent="true" noContentHelp="'standard help'">
                <t t-set-slot="no-content">
                    <div class="toy_no_content">nothing here</div>
                </t>
                <div class="toy_content"/>
            </ViewLayout>
        `;
        static components = { ViewLayout };
        props = useProps(this.constructor.props);
    }

    await mountWithSearch(ToyComponent, {
        resModel: "foo",
        searchViewId: false,
    });
    expect(`.o_content .toy_no_content`).toHaveCount(1);
    expect(`.o_content .o_view_nocontent`).toHaveCount(0);
    expect(`.o_content > .toy_content`).toHaveCount(1);
});

test(`EmptyState: the fallback takes a caller's title and description`, async () => {
    await mountWithCleanup(EmptyState, {
        props: { title: "No orders yet", description: "Create one from a quotation." },
    });
    expect(`.o_view_nocontent_empty_folder`).toHaveText("No orders yet");
    expect(`.o_nocontent_help p:eq(1)`).toHaveText("Create one from a quotation.");
});

test(`EmptyState: an action's help replaces the fallback`, async () => {
    await mountWithCleanup(EmptyState, {
        props: {
            noContentHelp: markup("<p class='custom_help'>Custom</p>"),
            title: "unused",
        },
    });
    expect(`.custom_help`).toHaveCount(1);
    expect(`.o_view_nocontent_empty_folder`).toHaveCount(0);
});
