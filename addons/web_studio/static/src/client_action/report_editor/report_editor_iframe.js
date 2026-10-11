/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useThrottleForAnimation } from "@web/core/utils/timing";
import { useStudioEditorContext } from "@web_studio/client_action/editor/studio_editor_context";
import { ErrorDisplay } from "@web_studio/client_action/report_editor/error_display";
import { getCssFromPaperFormat } from "@web_studio/client_action/report_editor/utils";

export class ReportEditorIframe extends Component {
    static components = { ErrorDisplay };
    static template = "web_studio.ReportEditor.Iframe";
    static props = {
        iframeKey: t.string(),
        iframeSource: t.string(),
        onIframeLoaded: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.studioContext = useStudioEditorContext();
        this.reportEditorModel = proxy(this.studioContext.reportEditorModel);
        this.iframeRef = elementRef();
        this.onContainerScroll = useThrottleForAnimation(() => {
            if (this.iframeRef.el?.contentDocument) {
                this.iframeRef.el.contentDocument.dispatchEvent(new Event("scroll"));
            }
        });
    }

    get paperFormatStyle() {
        const {
            margin_top,
            margin_left,
            margin_right,
            print_page_height,
            print_page_width,
        } = this.reportEditorModel.paperFormat;
        return getCssFromPaperFormat({
            margin_top,
            margin_left,
            margin_right,
            print_page_height,
            print_page_width,
        });
    }
    get iframeStyle() {
        const { print_page_height } = this.reportEditorModel.paperFormat;
        return getCssFromPaperFormat({ print_page_height });
    }

    get iframeSource() {
        return this.props.iframeSource;
    }

    get iframeKey() {
        return this.reportEditorModel.renderKey + "_" + (this.props.iframeKey || "");
    }

    async onIframeLoaded() {
        await this.resizeIframeContent({ iframeRef: this.iframeRef });
        this.props.onIframeLoaded({ iframeRef: this.iframeRef });
    }

    async resizeIframeContent({ iframeRef }) {
        const iframeEl = iframeRef.el;
        const iframeContent = iframeEl.contentDocument;

        const computeIframeHeight = () =>
            (iframeEl.style.height = iframeContent.body.scrollHeight + "px");

        const footer = iframeContent.querySelector(".footer");
        const footerStyle = footer?.style;
        if (footerStyle) {
            const { width } =
                iframeContent.querySelector(".page")?.getBoundingClientRect() || {};
            if (!footer.hasAttribute("oe-origin-style")) {
                footer.setAttribute(
                    "oe-origin-style",
                    footer.getAttribute("style") || "",
                );
            }
            if (width) {
                footerStyle.setProperty("width", `${width}px`);
            }
        }

        iframeContent.querySelector("html").style.overflow = "hidden";

        const proms = [];
        Array.from(iframeContent.querySelectorAll("img[src]") || []).forEach((img) => {
            if (img.complete) {
                return;
            }
            const prom = new Promise((resolve) => {
                img.onload = resolve;
            });
            proms.push(prom);
        });
        await Promise.all(proms);
        computeIframeHeight();
    }
}
