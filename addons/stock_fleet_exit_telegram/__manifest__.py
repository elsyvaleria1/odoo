{
    "name": "Vehicle Exits over Telegram",
    "version": "19.0.1.0.0",
    "category": "Supply Chain/Inventory",
    "summary": "Drivers ask for a vehicle route with /rutas and the authorisers decide it with Telegram buttons",
    "description": "Adds the /rutas bot command. A driver, the employee of their Odoo user, chooses the vehicle among those they hold or drove lately or by typing part of its plate, one or more route activities, the passengers riding along and the odometer, which the GPS suggests where a bridge reads it, optionally with a photo of the dashboard kept on the route; the route then asks to leave. Every vehicle exit authoriser with a linked chat gets the request with Authorise and Refuse buttons, decides it in their own name, and the driver and the other authorisers are told the outcome. Out, the same command adds an activity or a passenger, registers the return with the odometer, or closes the route where the vehicle stays, offering the place the GPS finds or the route's activities. Waiting, it withdraws the request. Requires a linked Telegram account, an Odoo user linked to an employee and inventory rights; the bot serves /rutas once the command is added to it.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "stock_fleet_exit",
        "telegram",
    ],
    "data": [
        "data/telegram_command_data.xml",
    ],
    "auto_install": True,
}
