/** @odoo-module native */
import { ProjectRightSidePanel } from "../components/project_right_side_panel/project_right_side_panel.js";

export const ProjectUpdateControllerMixin = (T) =>
    class ProjectUpdateController extends T {
        static components = {
            ...T.components,
            ProjectRightSidePanel,
        };

        get className() {
            return super.className + " o_controller_with_rightpanel";
        }
    };
