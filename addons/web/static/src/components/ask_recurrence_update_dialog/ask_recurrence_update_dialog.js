// @ts-check
/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { uniqueId } from "@web/core/utils/functions";
import { Dialog } from "@web/ui/dialog";

/**
 * Which occurrences of a recurrence an edit applies to.
 *
 * `calendar` and `planning` each carried their own copy of this component and
 * of its template, identical but for the dialog title and the three labels --
 * the vocabulary, which is the only part that is genuinely per-model. That part
 * is a prop here; the mechanism is not duplicated.
 */
export class AskRecurrenceUpdateDialog extends Component {
    static template = "web.AskRecurrenceUpdateDialog";
    static components = { Dialog };
    static props = {
        title: t.string(),
        choices: t.object(),
        confirm: t.function(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.groupId = uniqueId("o_recurrence_update_");
        this.state = proxy({ selected: Object.keys(this.props.choices)[0] });
    }

    confirm() {
        this.props.confirm(this.state.selected);
        this.props.close();
    }
}

export function askRecurrenceUpdate(dialogService, { title, choices }) {
    return new Promise((resolve) => {
        dialogService.add(
            AskRecurrenceUpdateDialog,
            { title, choices, confirm: resolve },
            { onClose: resolve.bind(null, false) },
        );
    });
}
