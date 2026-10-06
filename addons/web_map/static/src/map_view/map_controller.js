/** @odoo-module native */
import { Component, onWillStart, onWillUnmount, proxy, t, useProps } from "@odoo/owl";
import { useSetupAction } from "@web/core/action_hook";
import { makeLogger } from "@web/core/debug/debug_logger";
import { loadLeaflet } from "@web/core/lib/leaflet";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import { useModelWithSampleData } from "@web/model/model";
import { usePager } from "@web/search/pager_hook";
import { standardViewProps } from "@web/views/standard_view_props";
import { useViewChassis, ViewLayout } from "@web/views/view_components";
import {
    drillDownAction,
    drillDownContext,
    drillDownViews,
} from "@web/views/view_utils";

const log = makeLogger("map.controller");

export class MapController extends Component {
    static template = "web_map.MapView";
    static components = { ViewLayout };
    static props = {
        ...standardViewProps,
        Model: t.function(),
        modelParams: t.object(),
        Renderer: t.function(),
        buttonTemplate: t.string(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.config = useViewConfig();
        this.action = useService("action");

        /** @type {typeof MapModel} */
        const Model = this.props.Model;
        // `useState` so the controller template's `model.useSampleModel` read
        // subscribes it; it previously relied on the model's blanket deep render.
        const model = proxy(useModelWithSampleData(Model, this.props.modelParams));
        this.model = model;

        onWillUnmount(() => {
            this.model.stopFetchingCoordinates();
        });

        useSetupAction({
            getLocalState: () => this.model.metaData,
        });

        onWillStart(() => loadLeaflet());

        usePager(() => ({
            offset: this.model.metaData.offset,
            limit: this.model.metaData.limit,
            total: this.model.data.count,
            onUpdate: ({ offset, limit }) => this.model.load({ offset, limit }),
        }));
        this.chassis = useViewChassis(this);
    }

    /**
     * @returns {any}
     */
    get rendererProps() {
        return {
            model: this.model,
            onMarkerClick: this.openRecords.bind(this),
        };
    }

    /**
     * @param {number[]} ids
     * @param {boolean} [newWindow]
     */
    openRecords(ids, newWindow) {
        log.logic("openRecords", () => ({ ids, newWindow }));
        if (ids.length === 1) {
            return this.action.switchView("form", { resId: ids[0] }, { newWindow });
        }
        const actionViews = this.config.views;
        this.action.doAction(
            drillDownAction(
                {
                    title: this.config.getDisplayName() || _t("Untitled"),
                    resModel: this.props.resModel,
                },
                actionViews,
                {
                    domain: [["id", "in", ids]],
                    views: drillDownViews(actionViews),
                    context: drillDownContext(this.props.context),
                },
            ),
            { newWindow, viewType: "list" },
        );
    }
}
