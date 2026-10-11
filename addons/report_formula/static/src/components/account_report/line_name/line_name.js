/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { useAccountReportContext } from "@report_formula/components/account_report/account_report_context";
import { parseLineId } from "@report_formula/js/util";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";

export class AccountReportLineName extends Component {
    static template = "report_formula.AccountReportLineName";
    static props = { lineIndex: t.number(), line: t.object() };
    static components = {
        Dropdown,
        DropdownItem,
    };
    props = useProps(this.constructor.props);

    setup() {
        this.reportContext = useAccountReportContext();
        this.action = useService("action");
        this.orm = useService("orm");
        this.ui = useService("ui");
        this.controller = proxy(this.reportContext.controller);

        this.lineNameCell = elementRef();
    }

    get modelName() {
        return parseLineId(this.props.line.id).at(-1)[1];
    }

    get caretOptions() {
        return this.controller.caretOptions[this.props.line.caret_options];
    }

    get hasCaretOptions() {
        return this.caretOptions?.length > 0;
    }

    async caretAction(caretOption) {
        const res = await this.orm.call(
            "report.formula",
            "dispatch_report_action",
            [
                this.controller.options.report_id,
                this.controller.options,
                caretOption.action,
                {
                    line_id: this.props.line.id,
                    action_param: caretOption.action_param,
                },
            ],
            {
                context: this.controller.context,
            },
        );

        return this.action.doAction(res);
    }

    get lineNameClasses() {
        let classes = "text";

        if (this.props.line.unfoldable) {
            classes += " unfoldable";
        }

        if (this.props.line.is_draft) {
            classes += " draft";
        }

        if (this.props.line.class) {
            classes += ` ${this.props.line.class}`;
        }

        return classes;
    }

    async triggerAction() {
        const res = await this.orm.call(
            "report.formula",
            "execute_action",
            [
                this.controller.options.report_id,
                this.controller.options,
                {
                    id: this.props.line.id,
                    actionId: this.props.line.action_id,
                },
            ],
            {
                context: this.controller.context,
            },
        );

        return this.action.doAction(res);
    }

    async loadMore() {
        const newLines = await this.orm.call("report.formula", "get_expanded_lines", [
            this.controller.options.report_id,
            this.controller.options,
            this.props.line.parent_id,
            this.props.line.groupby,
            this.props.line.expand_function,
            this.props.line.progress,
            this.props.line.offset,
            this.props.line.horizontal_split_side,
        ]);

        this.controller.setLineVisibility(newLines);
        if (this.controller.areLinesOrdered()) {
            this.controller.updateLinesOrderIndexes(
                this.props.lineIndex,
                newLines,
                true,
            );
        }
        await this.controller.replaceLineWith(this.props.lineIndex, newLines);
    }

    toggleFoldable() {
        if (this.props.line.unfoldable) {
            if (this.props.line.unfolded) {
                this.controller.foldLine(this.props.lineIndex);
            } else {
                this.controller.unfoldLine(this.props.lineIndex);
            }
        }
    }
}
