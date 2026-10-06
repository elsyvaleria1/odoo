/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { useViewModel } from "@web/model/model";
import { COG_GROUP, isActWindowView } from "@web/search/cog_menu/cog_menu_group";
import { CogMenuItem } from "@web/search/cog_menu/cog_menu_item";

const cogMenuRegistry = registry.category("cogMenu");

export class GeneratePdfsCogMenu extends Component {
    static template = "hr_payroll.GeneratePdfsCogMenu";
    static components = { CogMenuItem };
    static props = {};
    props = useProps(this.constructor.props);

    setup() {
        this.model = useViewModel();
        this.action = useService("action");
        this.notification = useService("notification");
    }

    generatePdfs() {
        this.unhighlightDraftRecords();
        const selection = this.model.root.selection;
        const draftRecords = selection.length
            ? selection.filter((r) => r.data.state === "draft")
            : this.model.root.records.filter((r) => r.data.state === "draft");
        if (
            !selection.length &&
            this.model.root.records.length < this.model.root.count
        ) {
            this.notification.add(
                _t(
                    "Only the drafts currently loaded on screen will get a PDF; select rows to target a different set.",
                ),
                { type: "warning" },
            );
        }
        return this.action.doActionButton({
            type: "object",
            resModel: "hr.payroll.employee.declaration",
            name: "action_generate_pdf",
            resIds: draftRecords.map((r) => r.resId),
        });
    }

    highlightDraftRecords() {
        if (this.model.root.selection.length) {
            return;
        }
        const table_row = document.getElementsByClassName("o_data_row");
        this.model.root.records.forEach((draft_declaration, index) => {
            if (index + 1 > table_row.length) {
                return;
            }
            if (draft_declaration.data.state === "draft") {
                table_row[index].classList.add("table-info");
            }
        });
    }

    unhighlightDraftRecords() {
        Array.from(document.getElementsByClassName("o_data_row")).forEach((row) => {
            if (!row.classList.contains("o_data_row_selected")) {
                row.classList.remove("table-info");
            }
        });
    }
}

export const GeneratePdfsCogMenuItem = {
    Component: GeneratePdfsCogMenu,
    groupNumber: COG_GROUP.APP,
    isDisplayed: (env) =>
        env.searchModel.resModel === "hr.payroll.employee.declaration" &&
        isActWindowView(env, ["list"]) &&
        env.model.root.records.some((record) => record.data.state === "draft"),
};

cogMenuRegistry.add("generate-pdf-menu", GeneratePdfsCogMenuItem, { sequence: 10 });
