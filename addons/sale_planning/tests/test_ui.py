from odoo.tests import tagged

from .common import TestCommonSalePlanning
from odoo.addons.planning.tests.common import TestUiCommon


@tagged("post_install", "-at_install")
class TestSalePlanningUi(TestCommonSalePlanning, TestUiCommon):
    def test_01_ui_inherit(self):
        self.plannable_so.action_confirm()
        open_shift = self._create_open_shift_auto_plan_can_fill()
        self.start_tour("/", "sale_planning_test_tour", login="admin")
        self.assertTrue(open_shift.resource_id)
