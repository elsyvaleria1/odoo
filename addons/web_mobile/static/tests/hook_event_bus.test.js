import { expect, test } from "@odoo/hoot";
import { HookEventBus } from "@web_mobile/js/hook_event_bus";

test("HookEventBus: Test callback", async () => {
    const eventBus = new HookEventBus({
        onAddListener: () => expect.step("onAddListenerCallback"),
        onRemoveListener: () => expect.step("onRemoveListenerCallback"),
    });

    const eventName = "test_event";
    const listener1 = () => expect.step("listener1");
    const listener2 = () => expect.step("listener2");

    expect.verifySteps([]);

    eventBus.trigger(eventName, {});
    expect.verifySteps([]);

    eventBus.addEventListener(eventName, listener1);
    expect.verifySteps(["onAddListenerCallback"]);

    eventBus.trigger(eventName, {});
    expect.verifySteps(["listener1"]);

    eventBus.addEventListener(eventName, listener2);
    expect.verifySteps(["onAddListenerCallback"]);

    eventBus.trigger(eventName, {});
    expect.verifySteps(["listener1", "listener2"]);

    eventBus.removeEventListener(eventName, listener1);
    expect.verifySteps(["onRemoveListenerCallback"]);

    eventBus.trigger(eventName, {});
    expect.verifySteps(["listener2"]);

    eventBus.removeEventListener(eventName, listener2);
    expect.verifySteps(["onRemoveListenerCallback"]);

    eventBus.trigger(eventName, {});
    expect.verifySteps([]);
});
