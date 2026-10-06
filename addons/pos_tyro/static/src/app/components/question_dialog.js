/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/ui/dialog";

export class QuestionDialog extends Component {
    static template = "pos_tyro.QuestionDialog";
    static components = { Dialog };
    static props = {
        question: t.object({
            text: t.string(),
            options: t.array(t.string()),
            isError: t.boolean().optional(),
            isManualCancel: t.boolean().optional(),
        }),
        onClickAnswer: t.function(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);

    onClickOption(option) {
        this.props.onClickAnswer(option);
        this.props.close();
    }
}
