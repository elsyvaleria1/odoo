import {
    WORK_LOCATION_PRESENCE_WORDS,
    WORK_LOCATION_TYPES,
    workLocationPresence,
} from "@hr_homeworking/work_location_presence";
import {
    BASE_IM_STATUSES,
    baseImStatus,
    registeredImStatusDecorations,
} from "@mail/core/common/presence_status";
import { describe, expect, test } from "@odoo/hoot";

describe.current.tags("headless");

test("the icon table and mail's registry cannot drift apart", () => {
    const registered = registeredImStatusDecorations();
    expect(WORK_LOCATION_TYPES.length).toBeGreaterThan(0);
    expect(WORK_LOCATION_PRESENCE_WORDS.length).toBeGreaterThan(0);
    for (const locationType of WORK_LOCATION_TYPES) {
        for (const status of WORK_LOCATION_PRESENCE_WORDS) {
            const decorated = `${locationType}_${status}`;
            expect(workLocationPresence(decorated)).not.toBe(null, {
                message: `${decorated} must draw an icon`,
            });
            expect(registered.get(decorated)).toBe(status, {
                message: `${decorated} must be registered with mail as ${status}`,
            });
            expect(baseImStatus(decorated)).toBe(status);
        }
    }
});

test("every located status this module registers is a word mail knows", () => {
    for (const [decorated, base] of registeredImStatusDecorations()) {
        if (workLocationPresence(decorated)) {
            expect(BASE_IM_STATUSES).toInclude(base, { message: decorated });
        }
    }
});
