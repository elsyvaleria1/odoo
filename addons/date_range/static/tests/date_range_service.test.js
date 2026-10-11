import "@date_range/js/date_range_service";

import { describe, expect, test } from "@odoo/hoot";
import { makeMockEnv, onRpc } from "@web/../tests/web_test_helpers";

describe.current.tags("headless");

test("loadDateRanges re-fetches on every call instead of caching stale data", async () => {
    let call = 0;
    onRpc("date.range", "search_read", () => {
        call++;
        return [{ id: 1, name: `Range ${call}`, type_id: false }];
    });
    onRpc("date.range.type", "search_read", () => []);
    const env = await makeMockEnv();
    const service = env.services.date_range;

    const first = await service.loadDateRanges();
    expect(first.ranges[0].name).toBe("Range 1");

    const second = await service.loadDateRanges();
    expect(call).toBe(2);
    expect(second.ranges[0].name).toBe("Range 2");
});

test("loadDateRanges de-duplicates concurrent in-flight calls", async () => {
    let call = 0;
    onRpc("date.range", "search_read", () => {
        call++;
        return [{ id: 1, name: "Range", type_id: false }];
    });
    onRpc("date.range.type", "search_read", () => []);
    const env = await makeMockEnv();
    const service = env.services.date_range;

    const [first, second] = await Promise.all([
        service.loadDateRanges(),
        service.loadDateRanges(),
    ]);
    expect(call).toBe(1);
    expect(first).toBe(second);
});
