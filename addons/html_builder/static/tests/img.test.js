import { Img } from "@html_builder/core/img";
import { ImgGroup } from "@html_builder/core/img_group";
import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { animationFrame, Deferred } from "@odoo/hoot-dom";
import { Component, useProps, xml } from "@odoo/owl";
import { mountWithCleanup, patchWithCleanup } from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");

defineMailModels();
test("ImgGroup's inner Img components should not be blocked before src load", async () => {
    const defs = {
        img1: new Deferred(),
        img2: new Deferred(),
        img3: new Deferred(),
    };
    patchWithCleanup(Img.prototype, {
        loadImage() {
            return defs[this.props.class];
        },
    });
    class Container extends Component {
        static components = { ImgGroup, Img };
        static template = xml`
            <ImgGroup>
                <t t-foreach="Object.keys(this.defs)" t-as="key" t-key="key">
                    <Img src="''" class="key"/>
                </t>
            </ImgGroup>`;
        static props = {};
        props = useProps(this.constructor.props);

        setup() {
            this.defs = defs;
        }
    }
    await mountWithCleanup(Container);

    for (const key in defs) {
        expect("img").toHaveCount(0);
        defs[key].resolve();
        await animationFrame();
    }
    expect("img").toHaveCount(3);
});
