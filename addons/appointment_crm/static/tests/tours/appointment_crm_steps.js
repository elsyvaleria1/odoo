class AppointmentCrmSteps {
    _goToAppointment(name) {
        /** @param {String} name */
        return [
            {
                content: "Select the appointment.",
                trigger: `#appointment_type_id, a[title='Book ${name}']`,
                async run(actions) {
                    if (this.anchor.tagName === "SELECT") {
                        await actions.selectByLabel(name);
                        await actions.click(".o_appointment_select_button");
                    } else {
                        await actions.click();
                    }
                },
                expectUnloadPage: true,
            },
        ];
    }
}

export default AppointmentCrmSteps;
