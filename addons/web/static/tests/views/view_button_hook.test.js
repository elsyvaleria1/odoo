// @ts-check

import { expect, test } from "@odoo/hoot";
import { Component, useProps, xml } from "@odoo/owl";
import {
    contains,
    mockService,
    mountWithCleanup,
} from "@web/../tests/web_test_helpers";
import { Dropdown } from "@web/components/dropdown/dropdown";
import { DropdownItem } from "@web/components/dropdown/dropdown_item";
import { registry } from "@web/core/registry";
import { elementRef } from "@web/core/utils/element_ref";
import { useViewButtonContext } from "@web/core/view_button_context_hooks";
import { ViewButton } from "@web/views/view_button/view_button";
import { useViewButtons } from "@web/views/view_button/view_button_hook";

test("action can be prevented", async () => {
    registry.category("services").add(
        "action",
        {
            start() {
                return {
                    async doActionButton() {
                        expect.step("doActionButton");
                    },
                };
            },
        },
        { force: true },
    );

    let executeInHook;
    let executeInHandler;

    class MyComponent extends Component {
        static template = xml`<div t-ref="this.rootRef" t-on-click="this.onClick" class="myComponent">Some text</div>`;
        static props = null;
        props = useProps(this.constructor.props);
        setup() {
            const rootRef = (this.rootRef = elementRef());
            useViewButtons(rootRef, {
                beforeExecuteAction: () => {
                    expect.step("beforeExecuteAction in hook");
                    return executeInHook;
                },
            });
            this.viewButtonContext = useViewButtonContext();
        }

        onClick() {
            const getResParams = () => ({
                resIds: [3],
                resId: 3,
            });
            const clickParams = {};
            const beforeExecute = () => {
                expect.step("beforeExecuteAction on handler");
                return executeInHandler;
            };
            this.viewButtonContext.onClickViewButton({
                beforeExecute,
                getResParams,
                clickParams,
            });
        }
    }

    await mountWithCleanup(MyComponent);
    await contains(".myComponent").click();
    expect.verifySteps([
        "beforeExecuteAction on handler",
        "beforeExecuteAction in hook",
        "doActionButton",
    ]);

    executeInHook = false;
    await contains(".myComponent").click();
    expect.verifySteps([
        "beforeExecuteAction on handler",
        "beforeExecuteAction in hook",
    ]);

    executeInHandler = false;
    await contains(".myComponent").click();
    expect.verifySteps(["beforeExecuteAction on handler"]);
});

test("ViewButton clicked in Dropdown close the Dropdown", async () => {
    registry.category("services").add(
        "action",
        {
            start() {
                return {
                    async doActionButton() {
                        expect.step("doActionButton");
                    },
                };
            },
        },
        { force: true },
    );

    class MyComponent extends Component {
        static components = { Dropdown, DropdownItem, ViewButton };
        static template = xml`
            <div t-ref="this.rootRef" class="myComponent">
                <Dropdown>
                    <button>dropdown</button>
                    <DropdownItem>
                        <ViewButton tag="'a'" clickParams="{ type:'action' }" string="'coucou'" record="{ resId: 1 }" />
                    </DropdownItem>
                </Dropdown>
            </div>
        `;
        static props = null;
        props = useProps(this.constructor.props);
        setup() {
            const rootRef = (this.rootRef = elementRef());
            useViewButtons(rootRef);
        }
    }

    await mountWithCleanup(MyComponent);
    await contains(".dropdown-toggle").click();
    expect(".dropdown-menu").toHaveCount(1);

    await contains("a[type=action]").click();
    expect.verifySteps(["doActionButton"]);
    expect(".dropdown-menu").toHaveCount(0);
});

test("execute action in new window", async () => {
    mockService("action", {
        async doActionButton(params, options) {
            expect.step(options);
        },
    });

    class MyComponent extends Component {
        static template = xml`<div t-ref="this.rootRef" t-on-click="this.onClick" class="myComponent">Some text</div>`;
        static props = null;
        props = useProps(this.constructor.props);
        setup() {
            const rootRef = (this.rootRef = elementRef());
            useViewButtons(rootRef);
            this.viewButtonContext = useViewButtonContext();
        }

        onClick() {
            const getResParams = () => ({
                resIds: [3],
                resId: 3,
            });
            const clickParams = {};
            this.viewButtonContext.onClickViewButton({
                getResParams,
                clickParams,
                newWindow: true,
            });
        }
    }

    await mountWithCleanup(MyComponent);
    await contains(".myComponent").click({ ctrlKey: true });
    expect.verifySteps([{ newWindow: true }]);
});

test("execute action in new window - 2", async () => {
    mockService("action", {
        async doActionButton(params, options) {
            expect.step(options);
        },
    });

    class MyComponent extends Component {
        static components = { ViewButton };
        static template = xml`
                <div t-ref="this.rootRef" class="myComponent">
                    <ViewButton tag="'a'" clickParams="{ type:'action' }" string="'coucou'" record="{ resId: 1 }" />
                </div>`;
        static props = null;
        props = useProps(this.constructor.props);
        setup() {
            const rootRef = (this.rootRef = elementRef());
            useViewButtons(rootRef);
        }
    }

    await mountWithCleanup(MyComponent);
    await contains("a[type=action]").click({ ctrlKey: true });
    expect.verifySteps([{ newWindow: true }]);
});
