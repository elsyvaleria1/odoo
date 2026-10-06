/** @odoo-module native */
import { registry } from "@web/core/registry";

import { GeoengineArchParser } from "./geoengine_arch_parser.js";
import { GeoengineController } from "./geoengine_controller.js";
import { GeoengineModel } from "./geoengine_model.js";
import { GeoengineRenderer } from "./geoengine_renderer.js";

/**
 * @typedef {Object} ViewConfig
 * @property {string} type
 * @property {typeof GeoengineArchParser} ArchParser
 * @property {typeof GeoengineController} Controller
 * @property {typeof GeoengineModel} Model
 * @property {typeof GeoengineRenderer} Renderer
 * @property {Function} props
 */

/**
 * @typedef {Object} GenericViewProps
 * @property {XMLDocument} arch
 * @property {Object} relatedModels
 * @property {string} resModel
 * @property {Object} context
 * @property {Array} domain
 * @property {number} [limit]
 */

/**
 * @typedef {Object} GeoengineViewProps
 * @property {XMLDocument} arch
 * @property {Object} relatedModels
 * @property {string} resModel
 * @property {Object} context
 * @property {Array} domain
 * @property {typeof GeoengineModel} Model
 * @property {typeof GeoengineRenderer} Renderer
 * @property {Object} archInfo
 */

/**
 * @type {ViewConfig}
 */
export const geoengineView = {
    type: "geoengine",
    ArchParser: GeoengineArchParser,
    Controller: GeoengineController,
    Model: GeoengineModel,
    Renderer: GeoengineRenderer,

    /**
     * @param {GenericViewProps} genericProps
     * @param {ViewConfig} view
     * @returns {GeoengineViewProps}
     */
    props: (genericProps, view) => {
        const { ArchParser } = view;
        const { arch, relatedModels, resModel } = genericProps;
        const archInfo = new ArchParser().parse(arch, relatedModels, resModel);

        return {
            ...genericProps,
            Model: view.Model,
            Renderer: view.Renderer,
            archInfo,
        };
    },
};

registry.category("views").add("geoengine", geoengineView);
