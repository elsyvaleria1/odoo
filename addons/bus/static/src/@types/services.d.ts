declare module "services" {
    import { busParametersService } from "@bus/bus_parameters_service";
    import { sharedStorageService } from "@bus/shared_storage_service";
    import { multiTabService } from "@bus/multi_tab_service";
    import { outdatedPageWatcherService } from "@bus/outdated_page_watcher_service";
    import { busMonitoringservice } from "@bus/services/bus_monitoring_service";
    import { busService } from "@bus/services/bus_service";
    import { busLogsService } from "@bus/debug/bus_logs_service";
    import { presenceService } from "@bus/services/presence_service";
    import { workerService } from "@bus/services/worker_service";
    import { assetsWatchdogService } from "@bus/services/assets_watchdog_service";
    import { simpleNotificationService } from "@bus/simple_notification_service";

    export interface Services {
        "bus.monitoring_service": typeof busMonitoringservice;
        "bus.outdated_page_watcher": typeof outdatedPageWatcherService;
        "bus.parameters": typeof busParametersService;
        bus_service: typeof busService;
        "bus.logs_service": typeof busLogsService;
        shared_storage: typeof sharedStorageService;
        multi_tab: typeof multiTabService;
        presence: typeof presenceService;
        worker_service: typeof workerService;
        "bus.assets_watchdog": typeof assetsWatchdogService;
        simple_notification: typeof simpleNotificationService;
    }
}
