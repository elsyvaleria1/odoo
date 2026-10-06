import { MrpMenuDialog } from "@mrp_workorder/mrp_display/dialog/mrp_menu_dialog";
import { describe, expect, test } from "@odoo/hoot";
import { makeDialogMockEnv, mountWithCleanup } from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");

const GROUPS = { byproducts: false, uom: false, workorders: true, timer: false };

async function mountMenu(groups) {
    await makeDialogMockEnv();
    await mountWithCleanup(MrpMenuDialog, {
        props: {
            close: () => {},
            groups,
            params: { checks: [] },
            record: {
                resModel: "mrp.production",
                resId: 1,
                data: { working_state: "normal" },
            },
            reload: () => {},
            title: "Manufacturing Order",
            removeFromCache: () => {},
            registerProduction: () => {},
        },
    });
}

test("the MO card offers Add Work Order when work orders are enabled", async () => {
    await mountMenu({ ...GROUPS, workorders: true });
    expect("button:contains(Add Work Order)").toHaveCount(1);
});

test("the MO card hides Add Work Order when work orders are disabled", async () => {
    await mountMenu({ ...GROUPS, workorders: false });
    expect("button:contains(Add Work Order)").toHaveCount(0);
});
