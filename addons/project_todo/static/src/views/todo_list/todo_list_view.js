/** @odoo-module native */
import { TaskListRenderer } from "@project/components/task_list_renderer";
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list";

import { TodoListController } from "./todo_list_controller.js";

export const todoListView = {
    ...listView,
    Controller: TodoListController,
    Renderer: TaskListRenderer,
};

registry.category("views").add("todo_list", todoListView);
