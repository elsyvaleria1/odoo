/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import * as dates from "@web/core/l10n/dates";
import { evaluateBooleanExpr } from "@web/core/py_js/py";
import { Field } from "@web/fields/field";
import { Record } from "@web/model/record";
import { getFormattedRecord } from "@web/views/kanban";
import { ViewButton } from "@web/views/view_button";
import { compileViewTemplates } from "@web/views/view_compiler";

import { HierarchyCompiler } from "./hierarchy_compiler.js";

export class HierarchyCard extends Component {
    static components = {
        Record,
        Field,
        ViewButton,
    };
    static props = {
        node: t.object(),
        openRecord: t.function(),
        archInfo: t.object(),
        classNames: t.string().optional(""),
    };
    static template = "web_hierarchy.HierarchyCard";
    static Compiler = HierarchyCompiler;
    props = useProps(this.constructor.props);

    setup() {
        const { archInfo } = this.props;
        this.templates = compileViewTemplates(
            this.constructor.Compiler,
            archInfo.templateDocs,
        );
        this.evaluateBooleanExpr = evaluateBooleanExpr;
    }

    get classNames() {
        const classNames = [this.props.classNames];
        if (this.props.node.nodes.length) {
            classNames.push("o_hierarchy_node_unfolded");
        }
        return classNames.join(" ");
    }

    getRenderingContext(data) {
        return {
            context: data.record.context,
            JSON,
            dates,
            record: getFormattedRecord(data.record),
            __comp__: Object.assign(Object.create(this), { this: this }),
            __record__: data.record,
        };
    }

    onGlobalClick(ev, newWindow) {
        if (ev.target.closest("button")) {
            return;
        }
        this.props.openRecord(this.props.node, newWindow);
    }

    onClickArrowUp() {
        this.props.node.fetchParentNode();
    }

    onClickArrowDown() {
        if (this.props.node.nodes.length) {
            this.props.node.collapseChildNodes();
        } else {
            this.props.node.showChildNodes();
        }
    }
}
