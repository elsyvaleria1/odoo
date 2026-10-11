/** @odoo-module native */
import { useBuilderContext } from "@html_builder/core/builder_context";
import {
    Component,
    onWillStart,
    onWillUpdateProps,
    proxy,
    t,
    useProps,
    xml,
} from "@odoo/owl";
import { Cache } from "@web/core/utils/collections/cache";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

const svgCache = new Cache(async (src) => {
    let text;
    try {
        const response = await window.fetch(src);
        text = await response.text();
    } catch {
        text = "<svg></svg>";
    }
    const parser = new window.DOMParser();
    const xmlDoc = parser.parseFromString(text, "text/xml");
    return xmlDoc.getElementsByTagName("svg")[0];
}, JSON.stringify);

export class Img extends Component {
    static props = {
        src: t.string(),
        class: t.string().optional(),
        style: t.string().optional(),
        alt: t.string().optional(),
        attrs: t.object().optional(),
        svgCheck: t.boolean().optional(true),
    };
    static template = xml`
        <t t-if="this.state.loaded">
            <svg xmlns="http://www.w3.org/2000/svg" t-if="this.isSvg(this.props.src)" t-ref="this.svgRef"
                t-att-width="this.svg.width"
                t-att-viewBox="this.svg.viewBox"
                t-att-fill="this.svg.fill"
                class="hb-svg d-flex m-auto"
                t-att-class="this.props.class"
                t-att-style="this.props.style"
                t-att="this.props.attrs"/>
            <img t-else=""
                t-att-src="this.props.src"
                t-att-class="this.props.class"
                t-att-style="this.props.style"
                t-att-alt="this.props.alt"
                t-att="this.props.attrs"/>
        </t>
        `;
    props = useProps(this.constructor.props);

    setup() {
        this.builderContext = useBuilderContext();
        this.svgRef = elementRef();
        this.svg = {};
        this.state = proxy({ loaded: false });

        onWillStart(async () => this.handleImgLoad(this.props.src));
        onWillUpdateProps(async (nextProps) => {
            if (this.props.src !== nextProps.src) {
                await this.handleImgLoad(nextProps.src);
            }
        });
        useLayoutEffect(
            (imgLoaded) => {
                if (
                    imgLoaded &&
                    this.isSvg(this.props.src) &&
                    this.svg.children.length
                ) {
                    const children = [];
                    for (const child of this.svg.children) {
                        children.push(child.cloneNode(true));
                    }
                    this.svgRef.el.replaceChildren(...children);
                }
            },
            () => [this.state.loaded],
        );
    }

    async handleImgLoad(src) {
        const prom = this.isSvg(src) ? this.getSvg(src) : this.loadImage(src);
        if (this.isSvg(src)) {
            prom.then((svg) => {
                this.svg = svg;
            });
        }
        if (this.builderContext.imgGroup) {
            this.builderContext.imgGroup.addImgProm(prom);
            this.builderContext.imgGroup.loaded.then(() => {
                this.state.loaded = true;
            });
        } else {
            await prom;
            this.state.loaded = true;
        }
    }

    loadImage(src) {
        return new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = () => resolve({ status: "loaded" });
            img.onerror = () => resolve({ status: "error" });
            img.src = src;
        });
    }

    isSvg(src) {
        return this.props.svgCheck && src.split(".").pop() === "svg";
    }

    async getSvg(src) {
        const svgEl = (await svgCache.read(src)).cloneNode(true);
        return {
            viewBox: svgEl.getAttribute("viewBox"),
            width: svgEl.getAttribute("width") || "",
            fill: svgEl.getAttribute("fill") || "",
            children: svgEl.children,
        };
    }
}
