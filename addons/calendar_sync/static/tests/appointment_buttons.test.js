import { expect, test } from "@odoo/hoot";
import {
    contains,
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
} from "@web/../tests/web_test_helpers";

class AppointmentType extends models.Model {
    _name = "appointment.type";
    _records = [
        {
            id: 1,
            name: "Consultation",
            calendar_sync_connectors: [
                { code: "google", label: "Google", icon: "/google.svg" },
                { code: "microsoft", label: "Outlook", icon: "/outlook.svg" },
            ],
        },
    ];

    name = fields.Char();
    calendar_sync_connectors = fields.Json();
}

defineModels([AppointmentType]);

const ARCH = `
    <form>
        <field name="calendar_sync_connectors" invisible="1"/>
        <widget name="calendar_sync_appointment_buttons"/>
    </form>`;

test("a button per provider the staff may connect", async () => {
    await mountView({
        type: "form",
        resModel: "appointment.type",
        resId: 1,
        arch: ARCH,
    });
    expect(".o_appointment_sync_btn").toHaveCount(2);
    expect(".o_appointment_sync_btn:eq(0) span").toHaveText("Google");
    expect(".o_appointment_sync_btn:eq(1) span").toHaveText("Outlook");
});

test("each button synchronizes its own provider", async () => {
    onRpc("/calendar_sync/microsoft/sync_data", () => {
        expect.step("microsoft");
        return { status: "no_new_event" };
    });
    onRpc("/calendar_sync/google/sync_data", () => {
        expect.step("google");
        return { status: "no_new_event" };
    });
    await mountView({
        type: "form",
        resModel: "appointment.type",
        resId: 1,
        arch: ARCH,
    });
    await contains(".o_appointment_sync_btn:eq(1)").click();
    expect.verifySteps(["microsoft"]);
});
