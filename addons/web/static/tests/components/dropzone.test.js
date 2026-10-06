// @ts-check

import { expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import { Component, proxy, useProps, xml } from "@odoo/owl";
import { contains, mountWithCleanup } from "@web/../tests/web_test_helpers";
import { useDropzone } from "@web/components/dropzone/dropzone_hook";
import { elementRef } from "@web/core/utils/element_ref";

class Host extends Component {
    static template = xml`<div class="test-dropzone-host" t-ref="this.rootRef">host</div>`;
    static props = null;
    props = useProps(this.constructor.props);
    setup() {
        this.rootRef = elementRef();
        useDropzone(this.rootRef, () => expect.step("drop"));
    }
}

test("dropzone overlay appears while dragging files and handles the drop", async () => {
    await mountWithCleanup(Host);
    expect(".o-Dropzone").toHaveCount(0);

    const files = [new File(["hello"], "hello.txt", { type: "text/plain" })];
    await contains(".test-dropzone-host").dragEnterFiles(files);
    await animationFrame();
    expect(".o-Dropzone").toHaveCount(1);

    await contains(".o-Dropzone").dropFiles(files);
    await animationFrame();
    expect.verifySteps(["drop"]);
    expect(".o-Dropzone").toHaveCount(0);
});

test("dropzone overlay is removed when its owner is destroyed mid-drag", async () => {
    class Parent extends Component {
        static components = { Host };
        static template = xml`<Host t-if="this.state.show"/>`;
        static props = null;
        props = useProps(this.constructor.props);
        setup() {
            this.state = proxy({ show: true });
        }
    }
    const parent = await mountWithCleanup(Parent);

    const files = [new File(["hello"], "hello.txt", { type: "text/plain" })];
    await contains(".test-dropzone-host").dragEnterFiles(files);
    await animationFrame();
    expect(".o-Dropzone").toHaveCount(1);

    /** @type {any} */ (parent.state).show = false;
    await animationFrame();
    await animationFrame();
    expect(".o-Dropzone").toHaveCount(0);
});
