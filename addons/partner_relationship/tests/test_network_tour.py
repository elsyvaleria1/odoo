from odoo.tests import HttpCase, tagged

from .common import PartnerRelationCommon


@tagged("post_install", "-at_install")
class TestPartnerNetworkTour(PartnerRelationCommon, HttpCase):
    browser_size = "1920x1080"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.juan.name = "Juan Ramirez Solis"
        cls.household = cls.quick_ref("partner_relationship.relation_type_household")
        cls.business = cls.quick_ref(
            "partner_relationship.relation_type_businesspartner"
        )

        cls._create_relation(cls.juan, cls.type_sibling, cls.maria)
        cls._create_relation(cls.juan, cls.type_spouse, cls.lucia)
        cls._create_relation(cls.juan, cls.type_compadre, cls.pedro)
        cls._create_relation(cls.juan, cls.household, cls.stranger)
        cls._create_relation(
            cls.juan, cls.business, cls._create_person("Rosa", "female")
        )
        cls._create_relation(
            cls.juan, cls.type_crop, cls._create_person("Diego", "male")
        )

    def test_the_network_draws_and_its_legend_filters(self):
        self.start_tour(
            "/odoo",
            "partner_network_tour",
            login="admin",
        )
