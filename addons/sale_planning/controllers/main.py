from odoo.addons.planning.controllers.main import ShiftController


class ShiftControllerProject(ShiftController):
    def _planning_get(self, planning_token, employee_token, message=False):
        result = super()._planning_get(planning_token, employee_token, message)
        if not result:
            return None
        result["open_slot_has_sale_line"] = any(
            s.sale_line_id for s in result["open_slots_ids"]
        )
        result["unwanted_slot_has_sale_line"] = any(
            s.sale_line_id for s in result["unwanted_slots_ids"]
        )
        return result

    def _get_slot_sale_line(self, slot):
        if not slot.sale_line_id:
            return None
        return f"{slot.sale_line_id.display_name}"

    def _get_slot_title(self, slot):
        return " - ".join(
            x
            for x in (super()._get_slot_title(slot), self._get_slot_sale_line(slot))
            if x
        )

    def _prepare_slot_display_data(self, slot, is_open_shift):
        vals = super()._prepare_slot_display_data(slot, is_open_shift)
        vals["sale_line"] = self._get_slot_sale_line(slot)
        return vals
