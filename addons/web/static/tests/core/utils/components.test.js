// @ts-check

import { expect, getFixture, test } from "@odoo/hoot";
import { Component, useProps, xml } from "@odoo/owl";
import { mountWithCleanup } from "@web/../tests/web_test_helpers";
import { ErrorHandler } from "@web/core/utils/components";
import { useRender } from "@web/core/utils/render_hooks";

test("ErrorHandler component", async () => {
    class Boom extends Component {
        static template = xml`<div><t t-out="this.will.throw"/></div>`;
        static props = null;
        props = useProps(this.constructor.props);
    }

    class Parent extends Component {
        static template = xml`
            <div>
                <t t-if="this.flag">
                    <ErrorHandler onError="() => this.handleError()">
                        <Boom/>
                    </ErrorHandler>
                </t>
                <t t-else="">not boom</t>
            </div>
        `;
        static components = { Boom, ErrorHandler };
        static props = null;
        props = useProps(this.constructor.props);
        render = useRender();
        setup() {
            this.flag = true;
        }
        handleError() {
            this.flag = false;
            this.render();
        }
    }

    await mountWithCleanup(Parent, { noMainContainer: true });
    expect(getFixture()).toHaveText("not boom");
});
