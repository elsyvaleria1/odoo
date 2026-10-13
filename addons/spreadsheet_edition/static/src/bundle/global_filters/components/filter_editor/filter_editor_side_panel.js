/** @odoo-module native */
/** @ts-check */

import { components, stores } from "@odoo/o-spreadsheet";
import { Component, onWillStart, t, useProps } from "@odoo/owl";
import { useSpreadsheetEnv } from "@spreadsheet/hooks";
import { _t } from "@web/core/translation";

import { FilterEditorStore } from "../../filter_editor_store.js";
import { GlobalFilterFooter } from "../global_filter_footer/global_filter_footer.js";
import { FilterEditorFieldMatching } from "./filter_editor_field_matching.js";

const { Checkbox, Section, SidePanelCollapsible, TextInput, ValidationMessages } =
    components;
const { useLocalStore } = stores;

/**
 * @typedef {import("@spreadsheet").OdooField} OdooField
 * @typedef {import("@spreadsheet").FieldMatching} FieldMatching
 * @typedef {import("@spreadsheet").GlobalFilter} GlobalFilter
 * @typedef State
 * @property {boolean} saved
 * @property {string} label
 */

export class AbstractFilterEditorSidePanel extends Component {
    static template = "";
    static components = {
        SidePanelCollapsible,
        Checkbox,
        Section,
        TextInput,
        FilterEditorFieldMatching,
        GlobalFilterFooter,
        ValidationMessages,
    };
    static props = {
        id: t.string().optional(),
        label: t.string().optional(),
        fieldMatching: t.object().optional(),
        onCloseSidePanel: t.function().optional(),
    };
    props = useProps(this.constructor.props);
    env = useSpreadsheetEnv();

    setup() {
        this.store = useLocalStore(FilterEditorStore, this.props, this.type);
        onWillStart(async () => await this.store.loadData);
    }

    get type() {
        throw new Error("Not implemented by children");
    }

    /**
     * @param {String} label
     */
    setLabel(label) {
        this.store.update({ label });
    }

    updateDefaultValue(defaultValue) {
        if (Array.isArray(defaultValue) && defaultValue.length === 0) {
            this.store.update({ defaultValue: undefined });
        } else {
            this.store.update({ defaultValue });
        }
    }

    get footerProps() {
        return {
            onClickSave: !this.store.isValid
                ? undefined
                : () => {
                      const sourcePanel = `${this.constructor.name}_${this.props.id}`;
                      this.store.saveGlobalFilter(sourcePanel);
                  },
            onClickDelete: !this.props.id
                ? undefined
                : () => {
                      if (this.props.id) {
                          this.env.model.dispatch("REMOVE_GLOBAL_FILTER", {
                              id: this.props.id,
                          });
                      }
                      this.env.replaceSidePanel(
                          "GLOBAL_FILTERS_SIDE_PANEL",
                          `${this.constructor.name}_${this.props.id}`,
                      );
                  },
            onClickCancel: () => {
                this.env.replaceSidePanel(
                    "GLOBAL_FILTERS_SIDE_PANEL",
                    `${this.constructor.name}_${this.props.id}`,
                );
            },
        };
    }

    get invalidModel() {
        return _t(
            "At least one data source has an invalid model. Please delete it before editing this global filter.",
        );
    }
}
