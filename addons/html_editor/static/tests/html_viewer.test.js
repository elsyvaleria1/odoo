import { HtmlViewer } from "@html_editor/components/html_viewer/html_viewer";
import { expect, test } from "@odoo/hoot";
import { waitFor } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { Component, markup, useProps, xml } from "@odoo/owl";
import { mountWithCleanup } from "@web/../tests/web_test_helpers";
import { registry } from "@web/core/registry";
import { defineScope } from "@web/core/scope";
import { MainComponentsContainer } from "@web/ui/main_components_container";

test(`XML-like self-closing elements are fixed in a standalone HtmlViewer`, async () => {
    await mountWithCleanup(MainComponentsContainer);

    registry.category("main_components").add("mycomponent", {
        Component: HtmlViewer,
        props: {
            config: {
                value: markup(`<a href="#"/>outside<a href="#">inside</a>`),
            },
        },
    });
    await animationFrame();
    expect(".o_readonly").toHaveInnerHTML(
        `<a href="#" target="_blank" rel="noreferrer"></a>outside<a href="#" target="_blank" rel="noreferrer">inside</a>`,
    );
});

test(`copy from HtmlViewer must support application/vnd.odoo.odoo-editor`, async () => {
    await mountWithCleanup(MainComponentsContainer);

    registry.category("main_components").add("mycomponent", {
        Component: HtmlViewer,
        props: {
            config: {
                value: markup(`
                    <p>before</p>
                    <table class="table table-bordered o_table">
                        <tbody>
                            <tr style="height: 49.1875px;">
                                <td style="background-color: rgba(214, 239, 214, 0.6); color: rgb(55, 65, 81);">
                                    <p>A</p>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                    <p>after</p>
                `),
            },
        },
    });
    await animationFrame();
    const beforeNode = await waitFor("p:contains('before')");
    const afterNode = await waitFor("p:contains('after')");
    const range = new Range();
    range.setStart(beforeNode, 1);
    range.setEnd(afterNode, 0);
    getSelection().addRange(range);
    await animationFrame();

    const clipboardData = new DataTransfer();
    const ev = new ClipboardEvent("copy", { bubbles: true, clipboardData });
    beforeNode.dispatchEvent(ev);

    expect(clipboardData.getData("text/plain").trim()).toBe("A");
    expect(clipboardData.getData("text/html")).toInclude("background-color");
    expect(clipboardData.getData("application/vnd.odoo.odoo-editor")).toBe(
        clipboardData.getData("text/html"),
    );
});

test(`copy from HtmlViewer should copy all the selection`, async () => {
    await mountWithCleanup(MainComponentsContainer);

    registry.category("main_components").add("mycomponent", {
        Component: HtmlViewer,
        props: {
            config: {
                value: markup(`
                    <table class="table table-bordered o_table">
                        <tbody>
                            <tr style="height: 49.1875px;">
                                <td style="background-color: rgba(214, 239, 214, 0.6); color: rgb(55, 65, 81);">
                                    <p>A</p>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                `),
            },
        },
    });
    await animationFrame();
    const tableParent = (await waitFor("table")).parentElement;
    const range = new Range();
    range.setStart(tableParent, 0);
    range.setEnd(tableParent, 1);
    getSelection().addRange(range);
    await animationFrame();
    const clipboardData = new DataTransfer();
    tableParent.dispatchEvent(
        new ClipboardEvent("copy", { bubbles: true, clipboardData }),
    );

    expect(clipboardData.getData("text/html")).toInclude("table");
    expect(clipboardData.getData("application/vnd.odoo.odoo-editor")).toBe(
        clipboardData.getData("text/html"),
    );
});

test(`an embedded component reads the scopes its HtmlViewer reads`, async () => {
    const hostScope = defineScope("html_editor/tests/html_viewer_host");

    class Probe extends Component {
        static props = null;
        static template = xml`<span class="o_probe" t-out="this.value"/>`;
        props = useProps(this.constructor.props);

        setup() {
            this.value = hostScope.use().value;
        }
    }

    class Host extends Component {
        static components = { HtmlViewer };
        static props = null;
        static template = xml`<HtmlViewer config="this.config"/>`;
        props = useProps(this.constructor.props);

        setup() {
            hostScope.provide({ value: "provided above the viewer" });
            this.config = {
                value: markup(`<div data-embedded="probe"></div>`),
                embeddedComponents: [{ name: "probe", Component: Probe }],
            };
        }
    }

    await mountWithCleanup(Host);
    await waitFor(".o_probe");
    expect(".o_probe").toHaveText("provided above the viewer");
});
