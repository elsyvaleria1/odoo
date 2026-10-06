/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import * as dates from "@web/core/l10n/dates";
import { elementRef } from "@web/core/utils/element_ref";
import { Record } from "@web/model/record";
import { useViewButtons, ViewButton } from "@web/views/view_button";
import { compileViewTemplates } from "@web/views/view_compiler";

import { GanttCompiler } from "./gantt_compiler.js";

export class GanttPopover extends Component {
    static template = "web_gantt.GanttPopover";
    static components = { ViewButton, Record };
    static props = {
        title: t.any().optional(),
        displayGenericButtons: t.any(),
        bodyTemplate: t.any().optional(),
        footerTemplate: t.any().optional(),
        KanbanRecord: t.any().optional(),
        kanbanViewParams: t.any().optional(),
        resModel: t.any(),
        resId: t.any(),
        context: t.any(),
        close: t.any(),
        reloadOnClose: t.any(),
        buttons: t.any(),
        actionContext: t.any().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.rootRef = elementRef();

        this.templates = {};
        const toCompile = {};
        const { bodyTemplate, footerTemplate } = this.props;
        if (bodyTemplate) {
            toCompile.body = bodyTemplate;
        }
        if (footerTemplate) {
            toCompile.footer = footerTemplate;
        }
        Object.assign(
            this.templates,
            compileViewTemplates(GanttCompiler, toCompile, {
                recordExpr: "__record__",
            }),
        );

        useViewButtons(this.rootRef, {
            reload: () => {
                this.props.reloadOnClose();
                this.props.close();
            },
        });

        this.displayPopoverHeader = Boolean(this.templates.body);
        if (!this.templates.body) {
            const { kanbanViewParams, resId, resModel } = this.props;
            const { activeFields, archInfo, fields } = kanbanViewParams;
            this.recordProps = {
                resModel,
                resId,
                activeFields,
                fields,
                hooks: {
                    lifecycle: {
                        onRecordSaved: this.props.reloadOnClose,
                    },
                },
                context: this.props.actionContext,
            };
            this.kanbanRecordProps = { archInfo };
        }
    }

    get renderingContext() {
        return Object.assign({}, this.props.context, {
            __comp__: this,
            dates,
            __record__: { resModel: this.props.resModel, resId: this.props.resId },
        });
    }

    async onClick(button) {
        await button.onClick();
        this.props.close();
    }

    onCloseKeydown(ev) {
        if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            this.props.close();
        }
    }
}
