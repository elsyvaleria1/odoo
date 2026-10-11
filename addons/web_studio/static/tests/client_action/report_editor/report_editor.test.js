import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { hover, waitFor } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { Component, proxy, useProps, xml } from "@odoo/owl";
import {
    contains,
    makeMockEnv,
    mockService,
    mountWithCleanup,
    onRpc,
} from "@web/../tests/web_test_helpers";
import { useService } from "@web/core/utils/hooks";
import { onWillRender } from "@web/core/utils/render_hooks";
import { WebClient } from "@web/webclient/webclient";
import { provideStudioEditorContext } from "@web_studio/client_action/editor/studio_editor_context";
import { ReportEditorModel } from "@web_studio/client_action/report_editor/report_editor_model";
import { ReportEditorWysiwyg } from "@web_studio/client_action/report_editor/report_editor_wysiwyg/report_editor_wysiwyg";

import { defineStudioEnvironment } from "../../studio_tests_context.js";

describe.current.tags("desktop");

test("setting is in edition doesn't produce intempestive renders", async () => {
    defineMailModels();

    mockService("ui", {
        block: () => expect.step("block"),
        unblock: () => expect.step("unblock"),
    });

    const env = await makeMockEnv();

    class Child extends Component {
        static template = xml`<div class="child" t-out="this.props.rem.isInEdition"/>`;
        static props = null;
        props = useProps(this.constructor.props);
        setup() {
            onWillRender(() => expect.step("Child rendered"));
        }
    }

    class Parent extends Component {
        static components = { Child };
        static template = xml`
            <Child rem="this.rem" />
            <button class="test-btn" t-on-click="() => this.rem.setInEdition(false)">btn</button>
        `;
        static props = null;
        props = useProps(this.constructor.props);

        setup() {
            this.rem = proxy(
                new ReportEditorModel({ services: env.services, resModel: "partner" }),
            );
            onWillRender(() => expect.step("Parent rendered"));
            this.rem.setInEdition(true);
        }
    }

    await mountWithCleanup(Parent);
    await animationFrame();

    expect.verifySteps(["block", "Parent rendered", "Child rendered"]);
    expect(".child").toHaveText("true");

    await contains("button.test-btn").click();

    expect(".child").toHaveText("false");
    expect.verifySteps(["unblock", "Child rendered"]);
});

test("reports tab disabled when no record", async () => {
    defineStudioEnvironment();
    onRpc("ir.model", "studio_model_infos", ({ args }) => ({
        is_mail_thread: true,
        record_ids: [],
        name: "Custom Partner Model",
        model: args[0],
    }));
    await mountWithCleanup(WebClient);
    await contains("a.o_app[data-menu-xmlid=app_1]").click();
    await animationFrame();
    await contains(".o_web_studio_navbar_item").click();
    expect(".o_web_studio_menu .o_menu_sections button:contains(Reports)").toHaveCount(
        1,
    );
    expect(
        ".o_web_studio_menu .o_menu_sections button:contains(Reports):disabled",
    ).toHaveCount(1);
    await hover(".o_web_studio_menu .o_menu_sections button:contains(Reports)");
    await waitFor(".o-overlay-item", { timeout: 1000 });
    expect(".o-overlay-item").toHaveText(
        "You cannot edit a report while there is no Custom Partner Model (partner)",
    );
});

test("leaving the report editor saves a report name still being typed", async () => {
    defineMailModels();
    onRpc("/web_studio/save_report", async (request) => {
        const { params } = await request.json();
        expect.step(params.report_changes?.name ?? "nothing to save");
        return {};
    });

    class Host extends Component {
        static components = { ReportEditorWysiwyg };
        static template = xml`<ReportEditorWysiwyg t-if="this.state.open" paperFormatStyle="''"/>`;
        static props = null;
        props = useProps(this.constructor.props);

        setup() {
            this.state = proxy({ open: true });
            const services = {
                ui: useService("ui"),
                notification: useService("notification"),
            };
            const rem = new ReportEditorModel({
                services: {
                    ...services,
                    studio: { editedReport: { res_id: 1 } },
                    unProtectedNotification: services.notification,
                },
            });
            rem._isLoaded = true;
            rem._errorMessage = "no editor";
            rem._reportArchs.reportQweb =
                "<html><body><div id='wrapwrap'/></body></html>";
            rem._reportData = {
                id: 1,
                name: "Invoice",
                model: "partner",
                report_name: "partner.invoice",
                group_ids: [],
                paperformat_id: false,
                binding_model_id: false,
                attachment_use: false,
                attachment: false,
                display_in_print_menu: false,
            };
            provideStudioEditorContext({
                reportEditorModel: rem,
                editionFlow: proxy({}),
            });
        }
    }

    const host = await mountWithCleanup(Host);
    await contains(".o_web_studio_sidebar input#name").edit("Invoice (draft)", {
        confirm: false,
    });
    host.state.open = false;
    await expect.waitForSteps(["Invoice (draft)"]);
});
