import { describe, expect, test } from "@odoo/hoot";
import {
    asyncStep,
    makeMockEnv,
    restoreRegistry,
    waitForSteps,
} from "@web/../tests/web_test_helpers";
import { registry } from "@web/core/registry";

describe.current.tags("desktop");

test("multi tab allow to share values between tabs", async () => {
    const firstTabEnv = await makeMockEnv();
    restoreRegistry(registry);
    const secondTabEnv = await makeMockEnv(null, { makeNew: true });
    firstTabEnv.services.shared_storage.setSharedValue("foo", 1);
    expect(secondTabEnv.services.shared_storage.getSharedValue("foo")).toBe(1);
    firstTabEnv.services.shared_storage.setSharedValue("foo", 2);
    expect(secondTabEnv.services.shared_storage.getSharedValue("foo")).toBe(2);
    firstTabEnv.services.shared_storage.removeSharedValue("foo");
    expect(secondTabEnv.services.shared_storage.getSharedValue("foo")).toBe(undefined);
});

test("multi tab triggers shared_value_updated", async () => {
    const firstTabEnv = await makeMockEnv();
    restoreRegistry(registry);
    const secondTabEnv = await makeMockEnv(null, { makeNew: true });
    secondTabEnv.services.shared_storage.bus.addEventListener(
        "shared_value_updated",
        ({ detail }) => {
            asyncStep(`${detail.key} - ${JSON.parse(detail.newValue)}`);
        },
    );
    firstTabEnv.services.shared_storage.setSharedValue("foo", "bar");
    firstTabEnv.services.shared_storage.setSharedValue("foo", "foo");
    firstTabEnv.services.shared_storage.removeSharedValue("foo");
    await waitForSteps(["foo - bar", "foo - foo", "foo - null"]);
});

test("values stored under the historical 'undefined.' prefix are migrated", async () => {
    // The prefix used to be built from `this.name` (undefined on a service
    // value), so user preferences were persisted under literal
    // "undefined.<origin>." keys. Starting the service must migrate them to
    // the fixed "bus.<origin>." prefix instead of silently resetting them.
    const sanitizedOrigin = location.origin.replace(/:\/{0,2}/g, "_");
    localStorage.setItem(
        `undefined.${sanitizedOrigin}.mail.html_composer.enabled`,
        "true",
    );
    const env = await makeMockEnv();
    expect(
        env.services.shared_storage.getSharedValue("mail.html_composer.enabled"),
    ).toBe(true);
    expect(
        localStorage.getItem(`undefined.${sanitizedOrigin}.mail.html_composer.enabled`),
    ).toBe(null);
});
