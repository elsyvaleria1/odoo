/** @odoo-module native */
import { components, stores } from "@odoo/o-spreadsheet";
import { Component, onWillStart, onWillUpdateProps, t, useProps } from "@odoo/owl";
import { useSpreadsheetEnv } from "@spreadsheet/hooks";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";

import { SidePanelDomain } from "../../components/side_panel_domain/side_panel_domain.js";
import { RelatedFiltersSection } from "../../global_filters/components/related_filters_section/related_fitlers_section.js";
import { OdooPivotLayoutConfigurator } from "./odoo_pivot_layout_configurator/odoo_pivot_layout_configurator.js";

const { Checkbox, Section, ValidationMessages, PivotTitleSection, PivotDeferUpdate } =
    components;
const { useLocalStore, PivotSidePanelStore } = stores;

export class PivotDetailsSidePanel extends Component {
    static template = "spreadsheet_edition.PivotDetailsSidePanel";
    static components = {
        ValidationMessages,
        Checkbox,
        Section,
        OdooPivotLayoutConfigurator,
        PivotDeferUpdate,
        PivotTitleSection,
        RelatedFiltersSection,
        SidePanelDomain,
    };
    static props = { onCloseSidePanel: t.function(), pivotId: t.string() };
    props = useProps(this.constructor.props);
    env = useSpreadsheetEnv();

    setup() {
        this.notification = useService("notification");
        /**@type {PivotSidePanelStore} */
        this.store = useLocalStore(PivotSidePanelStore, this.props.pivotId);
        this.pivotSidePanelRef = elementRef();

        const loadData = async () => {
            await this.pivot.load();
            this.modelDisplayName =
                this.isModelValid && (await this.pivot.getModelLabel());
        };
        onWillStart(loadData);
        onWillUpdateProps(loadData);
    }

    get isModelValid() {
        return this.pivot.isModelValid();
    }

    /** @returns {import("@spreadsheet/pivot/odoo_pivot").default} */
    get pivot() {
        return this.store.pivot;
    }

    getScrollableContainerEl() {
        return this.pivotSidePanelRef.el;
    }

    /**
     * Get the last update date, formatted
     *
     * @returns {string} date formatted
     */
    getLastUpdate() {
        const lastUpdate = this.pivot.lastUpdate;
        if (lastUpdate) {
            return new Date(lastUpdate).toLocaleTimeString();
        }
        return _t("never");
    }

    onDomainUpdate(domain) {
        this.store.update({ domain });
    }

    get unusedPivotWarning() {
        return _t("This pivot is not used");
    }

    get invalidPivotModel() {
        const model = this.env.model.getters.getPivotCoreDefinition(
            this.props.pivotId,
        ).model;
        return _t(
            "The model (%(model)s) of this pivot is not valid (it may have been renamed/deleted). Please re-insert a new pivot.",
            {
                model,
            },
        );
    }

    get deferUpdatesLabel() {
        return _t("Defer updates");
    }

    get deferUpdatesTooltip() {
        return _t(
            "Changing the pivot definition requires to reload the data. It may take some time.",
        );
    }

    onDimensionsUpdated(definition) {
        this.store.update(definition);
    }

    flipAxis() {
        const { rows, columns } = this.store.definition;
        this.onDimensionsUpdated({
            rows: columns,
            columns: rows,
        });
    }

    delete() {
        this.env.model.dispatch("REMOVE_PIVOT", { pivotId: this.props.pivotId });
    }
}
