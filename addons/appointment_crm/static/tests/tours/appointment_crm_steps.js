class AppointmentCrmSteps {
    _goToAppointment(name) {
        /**
         * This method exists to be overridden as the steps to go to the
         * appointment change in sub-modules.
         * @param {String} name - The name of the appointment
         */
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
