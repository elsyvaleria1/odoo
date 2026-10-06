/** @odoo-module native */
import {
    provideBuilderContext,
    useBuilderContext,
} from "@html_builder/core/builder_context";
import { OptionsContainer } from "@html_builder/sidebar/option_container";
import { provideBuilderOptionsContext } from "@html_builder/utils/utils";
import { Component, proxy, t, useProps } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";

const log = makeLogger("website.builder.option.theme_tab");

export class ThemeTab extends Component {
    static template = "website.ThemeTab";
    static components = { OptionsContainer };
    static props = {
        colorPresetToShow: t
            .any() /* Number | null */
            .optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        useLifecycleLog(log);
        provideBuilderOptionsContext(() => [this.builderContext.editor.document.body]);
        provideBuilderContext({
            colorPresetToShow: this.props.colorPresetToShow,
        });
        this.builderContext = useBuilderContext();
        this.state = proxy({
            fontsData: {},
        });
        this.optionsContainers = this.builderContext.editor.resources["theme_options"];
        log.pipeline("setup theme option containers", () => ({
            count: this.optionsContainers?.length,
            colorPresetToShow: this.props.colorPresetToShow,
        }));
    }
}
