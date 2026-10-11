/** @odoo-module native */
import { BuilderAction } from "@html_builder/core/builder_action";
import { getShapeURL } from "@html_builder/plugins/image/image_helpers";
import { imageShapeDefinitions } from "@html_builder/plugins/image/image_shapes_definition";
import { handleImagesIfDataset } from "@html_builder/utils/image";
import { getValueFromVar } from "@html_builder/utils/utils";
import {
    getImageTransformationData,
    shouldPreventGifTransformation,
} from "@html_editor/main/media/image_post_process_plugin";
import { Plugin } from "@html_editor/plugin";
import { DEFAULT_PALETTE } from "@html_editor/utils/color";
import { getFetchedMimetype, getMimetype } from "@html_editor/utils/image";
import {
    activateCropper,
    createDataURL,
    cropperDataFields,
    isGif,
    loadImage,
    loadImageInfo,
} from "@html_editor/utils/image_processing";
import { withSequence } from "@html_editor/utils/resource";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { deepCopy, deepMerge } from "@web/core/utils/collections/objects";

import { applyFunDependOnSelectorAndExclude } from "../utils.js";

/**
 * @typedef {Object.<string, {
 *   label?: string,
 *   subgroups: Object.<string, {
 *     label?: string,
 *     shapes: Object.<string, {
 *       selectLabel?: string,
 *       animated?: boolean,
 *       transform?: boolean,
 *       isTechnical?: boolean,
 *       togglableRatio?: boolean,
 *     }>,
 *   }>,
 * }>} ImageShapeGroups
 * @typedef {((shapeGroups: ImageShapeGroups) => ImageShapeGroups | void)[]} image_shape_groups_providers
 * @typedef {((dataset: DOMStringMap) => string)[]} default_shape_handlers
 * @typedef {((
 *     svg: SVGElement,
 *     params: {
 *         shapeId: string,
 *         shapeFlip: "x" | "y",
 *         shapeRotate: 0 | "90" | "180" | "270",
 *         shapeAnimationSpeed: number,
 *         shapeColors: string,
 *     }
 * ) => Promise<void>)[]} post_compute_shape_listeners
 */

const CSS_ANIMATION_RULE_REGEX =
    /(?<declaration>animation(?:-duration)?:\s*.*?)(?<value>(?:\d+(?:\.\d+)?)|(?:\.\d+))(?<unit>ms|s)(?<separator>\s|;|"|$)/gm;
const SVG_DUR_TIMECOUNT_VAL_REGEX =
    /(?<attribute_name>\sdur="\s*)(?<value>(?:\d+(?:\.\d+)?)|(?:\.\d+))(?<unit>h|min|ms|s)?\s*"/gm;
const CSS_ANIMATION_RATIO_REGEX = /(--animation_ratio: (?<ratio>\d*(\.\d+)?));/m;
const MISSING_SHAPE_COLOR_SELECTORS =
    "img[data-shape]:not([data-shape-colors]), img[data-shape][data-shape-colors=';;;;']";

export class ImageShapeOptionPlugin extends Plugin {
    static id = "imageShapeOption";
    static dependencies = [
        "history",
        "userCommand",
        "imagePostProcess",
        "imageToolOption",
    ];
    static shared = [
        "resetShapeDataset",
        "getImageShapeGroups",
        "isTransformableShape",
        "isTechnicalShape",
        "isAnimableShape",
        "isTogglableRatioShape",
        "getShapeLabel",
        "loadShape",
    ];
    /** @type {import("plugins").BuilderResources} */
    resources = {
        builder_actions: {
            SetImageShapeAction,
            SetImgShapeColorAction,
            FlipImageShapeAction,
            RotateImageShapeAction,
            SetImageShapeSpeedAction,
            ResetImageShapeTransformationAction,
            ToggleImageShapeRatioAction,
        },
        process_image_warmup_handlers: this.processImageWarmup.bind(this),
        process_image_post_handlers: this.processImagePost.bind(this),
        hover_effect_allowed_predicates: (el) => this.canHaveHoverEffect(el),
        image_shape_groups_providers: withSequence(0, () =>
            deepCopy(imageShapeDefinitions),
        ),
        on_media_dialog_saved_handlers: withSequence(
            5,
            this.onMediaDialogSavedHandlers.bind(this),
        ),
        before_save_handlers: () =>
            applyFunDependOnSelectorAndExclude(
                this.cleanImageStaleDataset.bind(this),
                this.editable,
                {
                    selector: "img",
                    exclude: "[data-oe-type='image'] > img",
                },
            ),
        on_snippet_dropped_handlers: ({ snippetEl }) => {
            this.addShapeColorAttribute(snippetEl);
        },
    };
    setup() {
        this.shapeSvgTextCache = {};
        this.imageShapes = this.makeImageShapes();
        for (const shapeId of Object.keys(this.imageShapes)) {
            const oldShapeId = shapeId.replace("html_builder", "web_editor");
            this.imageShapes[oldShapeId] = this.imageShapes[shapeId];
        }
        this.addShapeColorAttribute(this.document);
    }
    /**
     * Compute and set default shape colors for images with data-shape but
     * missing data-shape-colors (e.g. s_cta_mockups, s_closer_look).
     *
     * @param {HTMLElement} editingElement - The element to search for images
     * with missing shape colors.
     */
    async addShapeColorAttribute(editingElement) {
        const missingShapeColorEls = editingElement.querySelectorAll(
            MISSING_SHAPE_COLOR_SELECTORS,
        );
        if (!missingShapeColorEls.length) {
            return;
        }
        for (const imgEl of missingShapeColorEls) {
            const shapeSvgText = await this.getShapeSvgText(imgEl.dataset.shape);
            const themedColor = this.getThemedSvgColors(shapeSvgText).join(";");
            if (themedColor !== ";;;;") {
                imgEl.dataset.shapeColors = themedColor;
            }
        }
    }
    async onMediaDialogSavedHandlers(elements, { node }) {
        const callback = async function (toProcessEl, nodeEl) {
            const data = await loadImageInfo(toProcessEl);
            if (!data.originalSrc) {
                return;
            }
            toProcessEl.dataset.shape = nodeEl.dataset.shape;
            for (const shapeInfo of ["shapeColors", "shapeFlip", "shapeRotate"]) {
                if (nodeEl.dataset[shapeInfo]) {
                    toProcessEl.dataset[shapeInfo] = nodeEl.dataset[shapeInfo];
                }
            }
        };
        await handleImagesIfDataset(elements, node, "shape", callback);
    }
    async canHaveHoverEffect(imgEl) {
        const dataset = Object.assign({}, imgEl.dataset, await loadImageInfo(imgEl));
        const isImageSupportedForShapes = await this.asyncIsImageSupportedForShapes(
            imgEl,
            dataset,
        );
        return (
            imgEl.tagName === "IMG" &&
            !this.isDeviceShape(imgEl) &&
            !this.isAnimableShape(dataset.shape) &&
            isImageSupportedForShapes
        );
    }
    isDeviceShape(img) {
        const shapeName = img.dataset.shape;
        if (!shapeName) {
            return false;
        }
        const shapeCategory = shapeName.split("/")[1];
        return shapeCategory === "devices";
    }
    isImageSupportedForShapes(img, dataset = img.dataset) {
        if (!!dataset.hoverEffect || !!dataset.shape) {
            return true;
        }
        if (!dataset.originalId) {
            return false;
        }
        return isImageSupportedForProcessing(getMimetype(img, dataset));
    }
    async asyncIsImageSupportedForShapes(img, dataset = img.dataset) {
        if (!!dataset.hoverEffect || !!dataset.shape) {
            return true;
        }
        if (!dataset.originalId) {
            return false;
        }
        return isImageSupportedForProcessing(await getFetchedMimetype(img, dataset));
    }
    async getShapeSvgText(shapeName) {
        const shape = shapeName.replace("web_editor", "html_builder");
        let shapeSvgText = this.shapeSvgTextCache[shape];
        if (shapeSvgText) {
            return shapeSvgText;
        }
        const shapeURL = getShapeURL(shape);
        shapeSvgText = await (await fetch(shapeURL)).text();
        this.shapeSvgTextCache[shape] = shapeSvgText;
        return shapeSvgText;
    }
    async loadShape(img, newData = {}) {
        return this.dependencies.imagePostProcess.processImage({
            img,
            newDataset: newData,
        });
    }
    async processImageWarmup(img, newDataset) {
        const getData = (propName) =>
            propName in newDataset ? newDataset[propName] : img.dataset[propName];
        const combinedDataset = { ...img.dataset, ...newDataset };
        const previousShapeId =
            img.dataset.shape || this.getDefaultShapeId(img.dataset);
        const shapeId =
            combinedDataset.shape || this.getDefaultShapeId(combinedDataset);
        if (!shapeId) {
            return;
        }
        const isNewShape = previousShapeId !== shapeId;
        const shapeSvgText = await this.getShapeSvgText(shapeId);

        const defaultShapeColors = this.getThemedSvgColors(shapeSvgText).join(";");
        newDataset.shapeColors =
            newDataset.shapeColors ??
            (isNewShape
                ? defaultShapeColors
                : (img.dataset.shapeColors ?? defaultShapeColors));

        const getNaturalWidth = async () => {
            if (img.naturalWidth) {
                return img.naturalWidth;
            }
            const loadedImgEl = await loadImage(img.getAttribute("src"));
            return loadedImgEl.naturalWidth;
        };
        const svgWidth =
            getData("resizeWidth") || getData("width") || (await getNaturalWidth());

        const svg = await this.computeShape(shapeSvgText, {
            ...img.dataset,
            ...newDataset,
            shapeId,
            shapeFlip: getData("shapeFlip") || "",
            shapeRotate: getData("shapeRotate") || 0,
            shapeAnimationSpeed: Number(getData("shapeAnimationSpeed")) || 0,
            shapeColors: newDataset.shapeColors,
        });

        const svgAspectRatio =
            parseInt(svg.getAttribute("width")) / parseInt(svg.getAttribute("height"));
        const imgAspectRatio = svg.dataset.imgAspectRatio;

        if (isNewShape && !("aspectRatio" in newDataset)) {
            const data = getImageTransformationData({ ...img.dataset, ...newDataset });

            const shouldBeSquared =
                this.imageShapes[shapeId].togglableRatio && !img.dataset.aspectRatio;
            if (shouldBeSquared && !shouldPreventGifTransformation(data)) {
                newDataset.aspectRatio = "1/1";
            }
        }

        /**
         * @param {HTMLCanvasElement} canvas
         */
        const postProcessCroppedCanvas = async (canvas) => {
            const img = await loadImage(canvas.toDataURL());
            document.createElement("div").appendChild(img);
            const [ratioWidth, ratioHeight] = imgAspectRatio.split(":");
            const shapeAspectRatio = parseFloat(ratioWidth) / parseFloat(ratioHeight);
            const cropper = await activateCropper(img, shapeAspectRatio, { y: 0 });
            const croppedCanvas = cropper.getCroppedCanvas();
            cropper.destroy();
            return croppedCanvas;
        };

        return {
            getHeight:
                svg.dataset.imgPerspective &&
                ((canvas) => canvas.width / svgAspectRatio),
            perspective: svg.dataset.imgPerspective || null,
            newDataset,
            postProcessCroppedCanvas: imgAspectRatio && postProcessCroppedCanvas,

            svg,
            svgAspectRatio,
            svgWidth,
        };
    }
    async processImagePost(b64url, handlerDataset, processContext) {
        const { svg, svgAspectRatio, svgWidth } = processContext;
        if (!svg) {
            return;
        }
        svg.querySelectorAll("image").forEach((image) => {
            image.setAttribute("xlink:href", b64url);
        });
        const loadedImage = await loadImage(b64url);
        if (!svg.dataset.forcedSize) {
            svg.setAttribute("width", loadedImage.naturalWidth);
            svg.setAttribute("height", loadedImage.naturalHeight);
        } else {
            const imageWidth = Math.trunc(svgWidth);
            const newHeight = imageWidth / svgAspectRatio;
            svg.setAttribute("width", imageWidth);
            svg.setAttribute("height", newHeight);
        }

        const blob = new Blob([svg.outerHTML], {
            type: "image/svg+xml",
        });
        const dataURL = await createDataURL(blob);
        return [dataURL, { ...handlerDataset, mimetype: "image/svg+xml" }];
    }

    /**
     * Builds the shape's SVG element by applying its colors, animation speed
     * and flip/rotate transformations.
     *
     * @param {string} svgText svg text file
     * @param {Object} params shape parameters (shapeId, shapeFlip,
     *                        shapeRotate, shapeAnimationSpeed, shapeColors)
     * @returns {SVGElement}
     */
    async computeShape(svgText, params) {
        const { shapeId, shapeFlip, shapeRotate, shapeAnimationSpeed, shapeColors } =
            params;
        svgText = this.replaceSvgColors(svgText, shapeColors.split(";"));
        if (shapeAnimationSpeed) {
            svgText = this.replaceAnimationDuration(svgText, shapeAnimationSpeed);
        }

        const svg = new DOMParser().parseFromString(
            svgText,
            "image/svg+xml",
        ).documentElement;

        if ((shapeFlip || shapeRotate) && this.isTransformableShape(shapeId)) {
            const shapeTransformValues = [];
            if (shapeFlip) {
                shapeTransformValues.push(
                    `scale${shapeFlip === "x" ? "X" : shapeFlip === "y" ? "Y" : ""}(-1)`,
                );
            }
            if (shapeRotate) {
                shapeTransformValues.push(`rotate(${shapeRotate}deg)`);
            }
            const transformOrigin = "transform-origin: 0.5px 0.5px;";
            svg.querySelector("#filterPath").setAttribute(
                "style",
                `transform: ${shapeTransformValues.join(" ")}; ${transformOrigin}`,
            );
        }

        for (const cb of this.getResource("post_compute_shape_listeners")) {
            await cb(svg, params);
        }

        svg.removeChild(svg.querySelector("#preview"));
        return svg;
    }
    /**
     * Replaces animation durations in both CSS animation rules and SVG
     * duration attributes of the given SVG string.
     *
     * @param {string} svgText The SVG string containing animations.
     * @param {number} speed The speed used to calculate the new animation
     *                       durations. If speed is 0.0, the original
     *                       durations are preserved.
     * @returns {string} The modified SVG string with updated animation
     *                   durations.
     */
    replaceAnimationDuration(svgText, speed) {
        const ratio = (speed >= 0.0 ? 1.0 + speed : 1.0 / (1.0 - speed)).toFixed(3);
        function callbackCssAnimationRule(match, declaration, value, unit, separator) {
            value = parseFloat(value) / (ratio ? ratio : 1);
            return `${declaration}${value}${unit}${separator}`;
        }

        function callbackSvgDurTimecountVal(match, attribute_name, value, unit) {
            value = parseFloat(value) / (ratio ? ratio : 1);
            return `${attribute_name}${value}${unit ? unit : "s"}"`;
        }

        svgText = svgText.replace(CSS_ANIMATION_RULE_REGEX, callbackCssAnimationRule);
        svgText = svgText.replace(
            SVG_DUR_TIMECOUNT_VAL_REGEX,
            callbackSvgDurTimecountVal,
        );
        if (CSS_ANIMATION_RATIO_REGEX.test(svgText)) {
            svgText = svgText.replace(
                CSS_ANIMATION_RATIO_REGEX,
                `--animation_ratio: ${ratio};`,
            );
        } else {
            const regex = /<svg .*>/m;
            const subst = `$&\n\t<style>\n\t\t:root { \n\t\t\t--animation_ratio: ${ratio};\n\t\t}\n\t</style>`;
            svgText = svgText.replace(regex, subst);
        }
        return svgText;
    }

    replaceSvgColors(shapeSvgText, colors) {
        const svgColors = this.getSvgColors(shapeSvgText);
        for (const [i, color] of colors.entries()) {
            if (svgColors[i] === null) {
                continue;
            }
            shapeSvgText = shapeSvgText.replace(
                new RegExp(svgColors[i], "g"),
                this.dependencies.imageToolOption.getCSSColorValue(color),
            );
        }
        return shapeSvgText;
    }
    getSvgColors(shapeSvgText) {
        return Object.values(DEFAULT_PALETTE).map((color) =>
            shapeSvgText.includes(color) ? color : null,
        );
    }
    getThemedSvgColors(shapeSvgText) {
        const svgColors = this.getSvgColors(shapeSvgText);
        return svgColors.map((color, i) =>
            color !== null
                ? this.dependencies.imageToolOption.getCSSColorValue(`o-color-${i + 1}`)
                : null,
        );
    }
    isTransformableShape(shapeId) {
        if (!shapeId) {
            return false;
        }
        const canTransform = this.imageShapes[shapeId].transform;
        return typeof canTransform === "undefined" ? true : canTransform;
    }
    isTechnicalShape(shapeId) {
        if (!shapeId) {
            return false;
        }
        return this.imageShapes[shapeId].isTechnical;
    }
    getShapeLabel(shapeId) {
        if (!shapeId) {
            return _t("None");
        }
        return this.imageShapes[shapeId].selectLabel || _t("None");
    }
    isAnimableShape(shape) {
        if (!shape) {
            return false;
        }
        return this.imageShapes[shape].animated;
    }
    isTogglableRatioShape(shape) {
        if (!shape) {
            return false;
        }
        return this.imageShapes[shape].togglableRatio;
    }
    getImageShapeGroups() {
        if (!this.imageShapeGroups) {
            const shapeGroups = {};
            for (const provider of this.getResource("image_shape_groups_providers")) {
                const providedGroups = provider(shapeGroups);
                if (providedGroups) {
                    Object.assign(shapeGroups, deepMerge(shapeGroups, providedGroups));
                }
            }
            this.imageShapeGroups = shapeGroups;
        }
        return this.imageShapeGroups;
    }
    makeImageShapes() {
        const entries = Object.values(this.getImageShapeGroups())
            .map((x) =>
                Object.values(x.subgroups)
                    .map((x) => Object.entries(x.shapes))
                    .flat(),
            )
            .flat();
        return Object.fromEntries(entries);
    }
    getDefaultShapeId(dataset) {
        for (const fn of this.getResource("default_shape_handlers")) {
            const shapeId = fn(dataset);
            if (shapeId) {
                return shapeId;
            }
        }
    }
    async cleanImageStaleDataset(imgEl) {
        const { originalSrc } = imgEl.dataset.originalSrc
            ? imgEl.dataset
            : await loadImageInfo(imgEl);
        if (!originalSrc) {
            delete imgEl.dataset.shape;
        }
        this.resetShapeDataset(imgEl, originalSrc);
    }

    resetShapeDataset(imgEl, originalSrc) {
        const shapeId = imgEl.dataset.shape;
        if (!shapeId) {
            const imgFilename = originalSrc?.split("/").pop().split(".")[0];
            if (
                !originalSrc ||
                (imgFilename && imgEl.dataset.fileName === `${imgFilename}.svg`)
            ) {
                delete imgEl.dataset.fileName;
            }
        }
        if (!this.isAnimableShape(shapeId)) {
            delete imgEl.dataset.shapeAnimationSpeed;
        }

        if (
            !shapeId ||
            (imgEl.dataset.shapeColors &&
                !imgEl.dataset.shapeColors.split(";").some((color) => color))
        ) {
            delete imgEl.dataset.shapeColors;
        }
        if (!this.isTransformableShape(shapeId)) {
            delete imgEl.dataset.shapeFlip;
            delete imgEl.dataset.shapeRotate;
        }
    }
}

export class SetImageShapeAction extends BuilderAction {
    static id = "setImageShape";
    static dependencies = ["imageShapeOption"];
    async load({ editingElement: img, value: shapeId }) {
        const params = {
            shape: shapeId,
            shapeFlip: undefined,
            shapeRotate: undefined,
        };
        if (
            !shapeId &&
            img.dataset.aspectRatio &&
            !cropperDataFields.some((field) => field in img.dataset)
        ) {
            params["aspectRatio"] = undefined;
        }
        return this.dependencies.imageShapeOption.loadShape(img, params);
    }
    apply({ editingElement: img, loadResult: updateImageAttributes }) {
        updateImageAttributes();
        const imgFilename = img.dataset.originalSrc.split("/").pop().split(".")[0];
        img.dataset.fileName = `${imgFilename}.svg`;
        this.dependencies.imageShapeOption.resetShapeDataset(
            img,
            img.dataset.originalSrc,
        );
    }
    isApplied({ editingElement: img, value }) {
        const datasetShape = img.dataset.shape;
        if (!datasetShape) {
            return false;
        }
        const currentShape = datasetShape.replace("web_editor", "html_builder");
        return currentShape === value;
    }
}
export class SetImgShapeColorAction extends BuilderAction {
    static id = "setImgShapeColor";
    static dependencies = ["imageShapeOption", "imageToolOption"];
    getValue({ editingElement: img, params: { index: colorIndex } }) {
        return img.dataset.shapeColors?.split(";")[colorIndex] || "";
    }
    async load({ editingElement: img, params: { index: colorIndex }, value: color }) {
        color = getValueFromVar(color);
        const newColorId = parseInt(colorIndex);
        const oldColors = img.dataset.shapeColors.split(";");
        const newColors = oldColors.slice(0);
        newColors[newColorId] = this.dependencies.imageToolOption.getCSSColorValue(
            color === "" ? `o-color-${newColorId + 1}` : color,
        );
        return this.dependencies.imageShapeOption.loadShape(img, {
            shapeColors: newColors.join(";"),
        });
    }
    apply({ loadResult: updateImageAttributes }) {
        updateImageAttributes();
    }
}
export class FlipImageShapeAction extends BuilderAction {
    static id = "flipImageShape";
    static dependencies = ["imageShapeOption"];
    async load({ editingElement: img, params: { axis } }) {
        const currentAxis = img.dataset.shapeFlip || "";
        const newAxis = currentAxis.includes(axis)
            ? currentAxis.replace(axis, "")
            : currentAxis + axis;
        return this.dependencies.imageShapeOption.loadShape(img, {
            shapeFlip: newAxis === "yx" ? "xy" : newAxis,
        });
    }
    apply({ loadResult: updateImageAttributes }) {
        updateImageAttributes();
    }
}

export class RotateImageShapeAction extends BuilderAction {
    static id = "rotateImageShape";
    static dependencies = ["imageShapeOption"];
    async load({ editingElement: img, params: { side } }) {
        const currentRotateValue = parseInt(img.dataset.shapeRotate) || 0;
        const rotation = side === "left" ? -90 : 90;
        const newRotateValue = (currentRotateValue + rotation + 360) % 360;
        return this.dependencies.imageShapeOption.loadShape(img, {
            shapeRotate: newRotateValue,
        });
    }
    apply({ loadResult: updateImageAttributes }) {
        updateImageAttributes();
    }
}
export class SetImageShapeSpeedAction extends BuilderAction {
    static id = "setImageShapeSpeed";
    static dependencies = ["imageShapeOption"];
    getValue({ editingElement: img }) {
        return img.dataset.shapeAnimationSpeed || 0;
    }
    async load({ editingElement: img, value: speed }) {
        return this.dependencies.imageShapeOption.loadShape(img, {
            shapeAnimationSpeed: speed,
        });
    }
    apply({ loadResult: updateImageAttributes }) {
        updateImageAttributes();
    }
}
export class ResetImageShapeTransformationAction extends BuilderAction {
    static id = "resetImageShapeTransformation";
    static dependencies = ["imageShapeOption"];
    async load({ editingElement: img }) {
        return this.dependencies.imageShapeOption.loadShape(img, {
            shapeFlip: undefined,
            shapeRotate: undefined,
        });
    }
    apply({ loadResult: updateImageAttributes }) {
        updateImageAttributes();
    }
}
export class ToggleImageShapeRatioAction extends BuilderAction {
    static id = "toggleImageShapeRatio";
    static dependencies = ["imageShapeOption"];

    isApplied({ editingElement: img }) {
        return img.dataset.aspectRatio !== "1/1";
    }
    async load({ editingElement: img }) {
        const isStretched = img.dataset.aspectRatio !== "1/1";
        return this.dependencies.imageShapeOption.loadShape(img, {
            aspectRatio: isStretched ? "1/1" : "0/0",
            x: undefined,
            y: undefined,
            width: undefined,
            height: undefined,
        });
    }
    apply({ editingElement: img, loadResult: updateImageAttributes }) {
        updateImageAttributes();
    }
}

registry
    .category("builder-plugins")
    .add(ImageShapeOptionPlugin.id, ImageShapeOptionPlugin);

/**
 * @param {String} mimetype
 * @param {Boolean} [strict=false] if true, even partially supported images (GIFs)
 *     won't be accepted.
 * @returns {Boolean}
 */
function isImageSupportedForProcessing(mimetype, strict = false) {
    if (isGif(mimetype)) {
        return !strict;
    }
    return ["image/jpeg", "image/png", "image/webp"].includes(mimetype);
}
