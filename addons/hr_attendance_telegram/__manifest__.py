{
    "name": "Telegram Attendance Commands",
    "version": "19.0.2.3.0",
    "oldest_upgradable_version": "19.0.2.2.0",
    "category": "Human Resources/Attendances",
    "summary": "Record attendance and lunch breaks from configured Telegram commands",
    "description": "Adds employee check-in, checkout and lunch commands with time parsing and attendance fields. Checkout can stop the employee’s active manufacturing work orders, and a scheduled action closes qualifying open attendances at day end. Requires enabled commands and an appropriate linked employee identity.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "telegram",
        "hr_attendance",
        "mrp",
    ],
    "data": [
        "security/res_groups.xml",
        "security/ir.access.csv",
        "data/telegram_command_data.xml",
        "data/ir_cron_data.xml",
        "views/hr_attendance_views.xml",
    ],
}
