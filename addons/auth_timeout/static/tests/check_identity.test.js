import { describe, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import {
    makeMockEnv,
    mockService,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { session } from "@web/session";

describe.current.tags("desktop");

test("a page under an inactivity lock reports its presence once the bus is up", async () => {
    patchWithCleanup(session, { lock_timeout_inactivity: 900 });
    mockService("bus_service", {
        start: async () => {},
        send: (eventName, data) =>
            expect.step(`${eventName}:${typeof data.inactivity_period}`),
    });
    await makeMockEnv();
    await animationFrame();
    await expect.waitForSteps(["update_presence:number"]);
});
