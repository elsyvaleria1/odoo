import { expect, test } from "@odoo/hoot";
import {
    getService,
    mockService,
    mountWithCleanup,
} from "@web/../tests/web_test_helpers";
import { WebClient } from "@web/webclient/webclient";

test("test Reader Loop", async () => {
    mockService("mobile", {
        enableReader: () => expect.step("enableReader"),
        stopReader: () => expect.step("stopReader"),
    });

    const eventName = "test_event";
    const listener1 = () => expect.step("listener1");
    const listener2 = () => expect.step("listener2");

    await mountWithCleanup(WebClient);
    const eventBus = await getService("mobile").bus;

    expect.verifySteps([]);

    eventBus.trigger(eventName, {});
    expect.verifySteps([]);

    eventBus.addEventListener(eventName, listener1);
    expect.verifySteps(["enableReader"]);

    eventBus.trigger(eventName, {});
    expect.verifySteps(["listener1"]);

    eventBus.addEventListener(eventName, listener2);
    eventBus.trigger(eventName, {});
    expect.verifySteps(["listener1", "listener2"]);

    eventBus.removeEventListener(eventName, listener1);
    eventBus.trigger(eventName, {});
    expect.verifySteps(["listener2"]);

    eventBus.removeEventListener(eventName, listener2);
    expect.verifySteps(["stopReader"]);

    eventBus.trigger(eventName, {});
    expect.verifySteps([]);
});
