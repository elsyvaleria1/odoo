from odoo.addons.planning.controllers.main import ShiftController


class ShiftControllerProject(ShiftController):
    def _planning_get(self, planning_token, employee_token, message=False):
        result = super()._planning_get(planning_token, employee_token, message)
        if not result:
            return None
        result["open_slot_has_project"] = any(
            s.project_id for s in result["open_slots_ids"]
        )
        result["unwanted_slot_has_project"] = any(
            s.project_id for s in result["unwanted_slots_ids"]
        )
        return result

    def _get_slot_title(self, slot):
        return " - ".join(
            x for x in (super()._get_slot_title(slot), slot.project_id.name) if x
        )

    def _prepare_slot_display_data(self, slot, is_open_shift):
        vals = super()._prepare_slot_display_data(slot, is_open_shift)
        vals["project"] = slot.project_id.name
        return vals
