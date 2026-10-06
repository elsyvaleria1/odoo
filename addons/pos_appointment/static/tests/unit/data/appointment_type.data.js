import { models } from "@web/../tests/web_test_helpers";

export class AppointmentType extends models.ServerModel {
    _name = "appointment.type";
    _records = [
        {
            id: 42,
            name: "Appointment with Jethalal",
        },
    ];
}
