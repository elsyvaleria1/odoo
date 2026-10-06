{
    "name": "Training Simulators",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Training",
    "summary": "Training games of every area, played on a read-only snapshot of real data",
    "description": "A catalogue of training simulators by area and the record of every session: who played, which scenario, how long, the errors and the result. Each simulator lives in its own module and plays on a snapshot of real data taken when the session starts; what happens in the game is kept only in the session, so production records are never touched. The tests of each simulator prove it with TrainingNeutralityCase.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "web",
    ],
    "data": [
        "security/training_simulator_security.xml",
        "security/ir.access.csv",
        "views/training_simulator_session_views.xml",
        "views/training_simulator_views.xml",
        "views/training_simulator_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "training_simulator/static/src/dashboard/**/*",
        ],
    },
    "application": True,
}
