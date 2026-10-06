import { activityGroupOpener } from "@mail/core/web/activity_group_opener";
import { describe, expect, test } from "@odoo/hoot";

describe.current.tags("headless");

test("an account.return activity group opens in kanban only", () => {
    expect(activityGroupOpener.availableViews({}, { model: "account.return" })).toEqual(
        [[false, "kanban"]],
    );
    expect(activityGroupOpener.availableViews({}, { model: "res.partner" })).toEqual([
        [false, "kanban"],
        [false, "list"],
        [false, "form"],
        [false, "activity"],
    ]);
});
