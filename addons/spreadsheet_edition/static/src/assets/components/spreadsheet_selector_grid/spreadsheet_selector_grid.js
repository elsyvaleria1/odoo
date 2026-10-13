/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { _t } from "@web/core/translation";
import { elementRef, noRef } from "@web/core/utils/element_ref";
import { useAutofocus } from "@web/core/utils/hooks";

const DEFAULT_LIMIT = 9;

export class SpreadsheetSelectorGrid extends Component {
    static template = "spreadsheet_edition.SpreadsheetSelectorGrid";

    static props = {
        spreadsheets: t.array(),
        onSpreadsheetSelected: t.function(),
        onSpreadsheetDblClicked: t.function(),
        getThumbnailURL: t.function(),
        selectedSpreadsheetId: t.any(),
        displayBlank: t.boolean().optional(true),
        blankCardLabel: t.string().optional(),
    };
    props = useProps(this.constructor.props);

    blankThumbnailPlaceholder = "/spreadsheet/static/img/spreadsheet.svg";

    setup() {
        this.autofocusRef = elementRef();
        this.noRef = noRef;
        useAutofocus({ ref: this.autofocusRef });
        useHotkey("ArrowRight", () => this._onArrowKey("right"), {
            allowRepeat: true,
        });
        useHotkey("ArrowLeft", () => this._onArrowKey("left"), {
            allowRepeat: true,
        });
    }

    get blankTemplate() {
        return {
            id: null,
            display_name: this.props.blankCardLabel ?? _t("Blank spreadsheet"),
            thumbnail: "/spreadsheet/static/img/spreadsheet.svg",
        };
    }

    /** @returns {Array} */
    get spreadsheets() {
        if (!this.props.displayBlank) {
            return this.props.spreadsheets;
        }
        return [this.blankTemplate, ...this.props.spreadsheets];
    }

    /** @returns {Number} */
    get itemsPerPage() {
        return this.props.displayBlank ? DEFAULT_LIMIT : DEFAULT_LIMIT + 1;
    }

    /** @param {"left"|"right"} direction */
    async _onArrowKey(direction) {
        const index = this.spreadsheets.findIndex(
            (spreadsheet) => spreadsheet.id === this.props.selectedSpreadsheetId,
        );

        const navigateToSpreadsheet = (newSpreadsheetId) => {
            if (newSpreadsheetId === this.props.selectedSpreadsheetId) {
                return;
            }
            this.props.onSpreadsheetSelected(newSpreadsheetId);
        };

        switch (direction) {
            case "left":
                if (index > 0 && index < this.spreadsheets.length) {
                    navigateToSpreadsheet(this.spreadsheets[index - 1].id);
                }
                break;
            case "right":
                if (index < this.spreadsheets.length - 1) {
                    navigateToSpreadsheet(this.spreadsheets[index + 1].id);
                }
                break;
            default:
                break;
        }
    }
}
