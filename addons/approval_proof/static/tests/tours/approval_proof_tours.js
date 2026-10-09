import { registry } from "@web/core/registry";

const PASSWORD = "approval_proof_tour_approver";

function proveWithPassword() {
    return [
        {
            content: "The proof dialog shows the request's amount",
            trigger: ".modal .o_proof_summary td:contains(1,500.00)",
        },
        {
            content: "Type the password",
            trigger: ".modal .o_proof_password input",
            run: `edit ${PASSWORD}`,
        },
        {
            content: "Confirm it is you",
            trigger: ".modal .o_proof_password button[type=submit]:enabled",
            run: "click",
        },
        {
            content: "The proof dialog is gone",
            trigger: "body:not(:has(.o_proof_summary))",
        },
    ];
}

registry.category("web_tour.tours").add("approval_proof_approve_tour", {
    steps: () => [
        {
            content: "Approve the request from its form",
            trigger: ".o_form_view .o_form_statusbar button[name='action_approve']",
            run: "click",
        },
        ...proveWithPassword(),
    ],
});

registry.category("web_tour.tours").add("approval_proof_refuse_tour", {
    steps: () => [
        {
            content: "Refuse the request from its form",
            trigger: ".o_form_view .o_form_statusbar button[name='action_refuse']",
            run: "click",
        },
        {
            content: "Pick the reason",
            trigger: ".modal .o_field_widget[name='refusal_reason_id'] input",
            run: "edit Count does not match",
        },
        {
            content: "Choose it",
            trigger: ".o-autocomplete--dropdown-item a:contains(Count does not match)",
            run: "click",
        },
        {
            content: "Confirm the refusal",
            trigger: ".modal button[name='action_confirm_refuse']",
            run: "click",
        },
        ...proveWithPassword(),
    ],
});

registry.category("web_tour.tours").add("approval_proof_activity_tour", {
    steps: () => [
        {
            content: "Approve from the approval activity in the chatter",
            trigger: ".o-mail-Activity button.btn-success:contains(Approve)",
            run: "click",
        },
        ...proveWithPassword(),
        {
            content: "The activity is done",
            trigger: ".o-mail-Chatter:not(:has(.o-mail-Activity button.btn-success))",
        },
    ],
});
