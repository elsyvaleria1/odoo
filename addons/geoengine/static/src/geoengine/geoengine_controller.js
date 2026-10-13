/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { _t } from "@web/core/translation";
import { useOwnedDialogs, useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { useViewConfig } from "@web/core/view_config_hooks";
import { useModelWithSampleData } from "@web/model/model";
import { extractFieldsFromArchInfo } from "@web/model/relational_model";
import { usePager } from "@web/search/pager_hook";
import { session } from "@web/session";
import { standardViewProps } from "@web/views/standard_view_props";
import { useViewChassis, ViewLayout } from "@web/views/view_components";
import { FormViewDialog } from "@web/views/view_dialogs";
import { useControllerServices } from "@web/views/view_utils";

import { makeGeoLogger } from "../geo_debug.js";

const debugLog = makeGeoLogger("GeoengineController");
const log = debugLog.log;

const DEFAULT_MAP_LIMIT = 1000;

export class GeoengineController extends Component {
    static template = "geoengine.GeoengineController";
    static components = { ViewLayout };
    static props = {
        ...standardViewProps,
        Model: t.function(),
        Renderer: t.function(),
        archInfo: t.object(),
    };
    props = useProps(this.constructor.props);
    /**
     * @param {Object} extractedActiveFields
     * @param {Object} archInfo
     * @returns {Object}
     */
    _configureActiveFields(extractedActiveFields, archInfo) {
        const activeFields = { ...extractedActiveFields };

        if (archInfo.webglTrail) {
            const timestampsField = archInfo.trailTimestampsField || "trail_timestamps";
            if (!(timestampsField in activeFields)) {
                activeFields[timestampsField] = {
                    name: timestampsField,
                    context: "{}",
                    required: false,
                    readonly: true,
                };
                debugLog("Added WebGL trail timestamps field:", timestampsField);
            }

            const colorField = archInfo.trailColorField || "trail_color";
            if (!(colorField in activeFields)) {
                activeFields[colorField] = {
                    name: colorField,
                    context: "{}",
                    required: false,
                    readonly: true,
                };
                debugLog("Added WebGL trail color field:", colorField);
            }
        }

        if (!("id" in activeFields)) {
            activeFields.id = {
                context: "{}",
                forceSave: false,
                invisible: true,
                isHandle: false,
                onChange: false,
                readonly: true,
                required: false,
            };
        }

        debugLog("ActiveFields configured:", Object.keys(activeFields));
        return activeFields;
    }

    /**
     * @returns {number|false}
     */
    get geoViewId() {
        if (this.props.viewId) {
            return this.props.viewId;
        }
        const entry = (this.config.views || []).find(
            ([, type]) => type === "geoengine",
        );
        return entry ? entry[0] : false;
    }

    get modelParams() {
        const { resModel, archInfo, defaultGroupBy } = this.props;
        const { fields, activeFields: extractedActiveFields } =
            extractFieldsFromArchInfo(archInfo, this.props.fields);

        const activeFields = this._configureActiveFields(
            extractedActiveFields,
            archInfo,
        );

        const modelConfig = this.props.state?.modelState?.config || {
            resModel,
            fields,
            activeFields,
            openGroupsByDefault: true,
        };

        return {
            config: modelConfig,
            geoViewId: this.geoViewId,
            state: this.props.state?.modelState || null,
            limit: archInfo.limit || DEFAULT_MAP_LIMIT,
            countLimit: archInfo.countLimit,
            defaultOrderBy: archInfo.defaultOrder,
            defaultGroupBy: this.searchMenuTypes.includes("groupBy")
                ? defaultGroupBy
                : false,
            activeIdsLimit: session.active_ids_limit,
            hooks: {
                ui: this._uiHooks,
            },
        };
    }

    setup() {
        this.config = useViewConfig();
        useLifecycleLog(log);
        const { action, dialog, notification, orm, uiHooks } = useControllerServices();
        this.actionService = action;
        this.dialog = dialog;
        this.notification = notification;
        this.orm = orm;
        this._uiHooks = uiHooks;
        this.view = useService("view");
        this.addDialog = useOwnedDialogs();
        this.chassis = useViewChassis(this);

        this._geoFieldKey = null;

        this.searchMenuTypes = this.props.searchMenuTypes || [];

        debugLog("Arch info:", this.props.archInfo);

        this.model = proxy(useModelWithSampleData(this.props.Model, this.modelParams));

        usePager(() => {
            if (this.model.drawsEveryMatch()) {
                return null;
            }
            const list = this.model.root;
            const { count, limit, offset } = list;
            return {
                offset,
                limit,
                total: count,
                onUpdate: async ({ offset, limit }) => {
                    await list.load({ limit, offset });
                },
            };
        });

        this._truncationReported = false;
        useLayoutEffect(
            () => this._warnIfTruncated(),
            () => [
                this.model.root.count,
                this.model.root.records.length,
                this.model.root.data,
            ],
        );
    }

    _warnIfTruncated() {
        const { count, records, data } = this.model.root;
        if (
            this._truncationReported ||
            !data ||
            !count ||
            records.length >= count ||
            this.model.drawsEveryMatch()
        ) {
            return;
        }
        this._truncationReported = true;
        this.notification.add(
            _t(
                "This map is showing %(shown)s of %(total)s records. Raise the view's " +
                    "limit, or narrow the search, to see them all.",
                { shown: records.length, total: count },
            ),
            { title: _t("Not all records are on the map"), type: "warning" },
        );
    }

    /**
     * @param {string} resModel
     * @param {number} resId
     * @param {Array|boolean} [viewId]
     */
    async openRecord(resModel, resId, viewId) {
        log.logic("openRecord", () => ({ resModel, resId, viewId }));
        const formViewId =
            viewId ||
            (
                await this.view.loadViews({
                    resModel,
                    views: [[false, "form"]],
                })
            ).views.form.id;
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: resModel,
            views: [[formViewId, "form"]],
            res_id: resId,
            target: "new",
            context: { edit: false, create: false },
        });
    }

    /**
     * @param {string} resModel
     * @param {string} field
     * @param {string} value
     */
    async createRecord(resModel, field, value) {
        const { views } = await this.view.loadViews({
            resModel,
            views: [[false, "form"]],
        });
        const context = {};
        context[`default_${field}`] = value;
        this.addDialog(FormViewDialog, {
            resModel,
            title: _t("New record"),
            viewId: views.form.id,
            context,
            onRecordSaved: () => this.onSaveRecord(),
        });
    }

    async onSaveRecord() {
        await this.model.root.load();
    }

    async onClickSave() {
        if (!this.model.root.editedRecord) {
            debugLog("No record being edited, ignoring save");
            return;
        }
        await this.model.root.editedRecord.save();
    }

    async onClickDiscard() {
        if (!this.model.root.editedRecord) {
            debugLog("No record being edited, ignoring discard");
            return;
        }
        await this.model.root.editedRecord.discard();
    }

    /**
     * @returns {string|undefined}
     */
    get geoFieldKey() {
        if (this._geoFieldKey === null) {
            const declared = this.props.archInfo.fieldNodes || {};
            const fields = this.model.root.fields;
            this._geoFieldKey =
                Object.keys(declared).find(
                    (name) => fields[name]?.geo_type !== undefined,
                ) ||
                Object.keys(fields).find(
                    (name) => fields[name].geo_type !== undefined,
                ) ||
                false;
            debugLog("Geo field key resolved:", this._geoFieldKey);
        }
        return this._geoFieldKey;
    }

    /**
     * @param {string} value
     * @param {string} [geoField]
     */
    async updateRecord(value, geoField = this.geoFieldKey) {
        log.logic("updateRecord", () => ({
            geoField,
            hasValue: Boolean(value),
        }));
        if (!geoField) {
            debugLog("No geometry field found, cannot update record");
            return;
        }
        if (!this.model.root.editedRecord) {
            debugLog("No record being edited, cannot update geometry");
            return;
        }
        await this.model.root.editedRecord.update({ [geoField]: value });
    }

    onDrawStart() {
        const { count, records } = this.model.root;
        if (records.length < count) {
            this.notification.add(
                _t(
                    "%(shown)s of %(total)s records are on the map. Anything you draw may overlap a record you cannot see.",
                    { shown: records.length, total: count },
                ),
                { title: _t("Not all records are displayed"), type: "warning" },
            );
        }
    }

    get rendererProps() {
        return {
            model: this.model,
            archInfo: this.props.archInfo,
            openRecord: this.openRecord.bind(this),
            geoFieldKey: this.geoFieldKey,
            createRecord: this.createRecord.bind(this),
            updateRecord: this.updateRecord.bind(this),
            onDrawStart: this.onDrawStart.bind(this),
            onClickDiscard: this.onClickDiscard.bind(this),
        };
    }
}
