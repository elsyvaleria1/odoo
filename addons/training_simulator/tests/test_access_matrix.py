from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestTrainingSimulatorAccessMatrix(AccessMatrixCase):
    personas = {
        "player_a": Persona("training_simulator.group_training_player"),
        "other_player_a": Persona("training_simulator.group_training_player"),
        "instructor_a": Persona("training_simulator.group_training_instructor"),
        "instructor_b": Persona(
            "training_simulator.group_training_instructor", company="b"
        ),
        "internal_a": Persona("base.group_user"),
    }
    cells = (
        Cell(
            "training.simulator",
            "simulator",
            note="one catalogue every company plays from: a player reads it, an "
            "instructor of any company configures it",
            player_a="r",
            other_player_a="r",
            instructor_a="rwcd",
            instructor_b="rwcd",
            internal_a="",
        ),
        Cell(
            "training.simulator.session",
            "session_a",
            note="a player plays their own sessions; an instructor sees those "
            "of the companies they work in, since a session keeps a snapshot "
            "of that company's data",
            player_a="rwc",
            other_player_a="",
            instructor_a="rwcd",
            instructor_b="",
            internal_a="",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        simulator = cls.env["training.simulator"].create(
            {
                "name": "matrix simulator",
                "code": "matrix_simulator",
                "play_route": "/odoo",
            }
        )
        session = cls.env["training.simulator.session"].create(
            {
                "simulator_id": simulator.id,
                "user_id": cls.users["player_a"].id,
                "company_id": cls.companies["a"].id,
            }
        )
        return {"simulator": simulator, "session_a": session}
