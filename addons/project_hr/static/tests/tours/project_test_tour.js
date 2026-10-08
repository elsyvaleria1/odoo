import "@project/../tests/tours/project_tour";

import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";

const EMPLOYEE_TRIGGERS = {
    'div[name="user_ids"].o_field_many2many_tags_avatar input':
        'div[name="employee_ids"].o_field_many2many_tags input',
    "ul.ui-autocomplete a .o_avatar_many2x_autocomplete":
        'div[name="employee_ids"] .o-autocomplete--dropdown-item:first-child a',
    ".o_field_many2many_tags_avatar .o_m2m_avatar": 'div[name="employee_ids"] .o_tag',
};

patch(registry.category("web_tour.tours").get("project_test_tour"), {
    steps() {
        return super
            .steps()
            .map((step) =>
                step.trigger in EMPLOYEE_TRIGGERS
                    ? { ...step, trigger: EMPLOYEE_TRIGGERS[step.trigger] }
                    : step,
            );
    },
});
