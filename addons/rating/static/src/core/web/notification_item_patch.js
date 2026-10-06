/** @odoo-module native */
import { NotificationItem } from "@mail/core/public_web/notification_item";
import { t } from "@odoo/owl";

NotificationItem.props.rating = t.any().optional();
