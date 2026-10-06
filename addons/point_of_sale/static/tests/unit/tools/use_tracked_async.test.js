import { expect, test } from "@odoo/hoot";
import { Component, useProps, xml } from "@odoo/owl";
import { useTrackedAsync } from "@point_of_sale/app/hooks/hooks";
import { mountWithCleanup } from "@web/../tests/web_test_helpers";

import { definePosModels } from "../data/generate_model_definitions.js";
import { setupPosEnv } from "../utils.js";

definePosModels();

test("useTrackedAsync keepLast ignores a stale slow response", async () => {
    await setupPosEnv();

    class Dummy extends Component {
        static template = xml`<div/>`;
        static props = {};
        props = useProps(this.constructor.props);
        setup() {
            this.tracked = useTrackedAsync((deferred) => deferred.promise, {
                keepLast: true,
            });
        }
    }
    const comp = await mountWithCleanup(Dummy, { props: {} });

    const slow = Promise.withResolvers();
    const fast = Promise.withResolvers();
    comp.tracked.call(slow);
    comp.tracked.call(fast);

    fast.resolve("fast");
    await Promise.resolve();
    await Promise.resolve();
    expect(comp.tracked.status).toBe("success");
    expect(comp.tracked.result).toBe("fast");

    slow.resolve("slow");
    await Promise.resolve();
    await Promise.resolve();
    expect(comp.tracked.result).toBe("fast");
    expect(comp.tracked.status).toBe("success");
});
