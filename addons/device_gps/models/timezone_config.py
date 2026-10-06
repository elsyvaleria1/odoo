from odoo import api, models


class ResCompany(models.Model):
    _inherit = "res.company"

    def write(self, vals):
        result = super().write(vals)
        if "partner_id" in vals:
            self.env["device.data.log.gps.report"]._rolling_mark_stale()
        return result


class ResPartner(models.Model):
    _inherit = "res.partner"

    def write(self, vals):
        result = super().write(vals)
        if "tz" in vals and self.env["res.company"].sudo().search_count(
            [("partner_id", "in", self.ids)], limit=1
        ):
            self.env["device.data.log.gps.report"]._rolling_mark_stale()
        return result


class ResourceConfig(models.Model):
    _inherit = "resource.config"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env["device.data.log.gps.report"]._rolling_mark_stale()
        return records

    def unlink(self):
        result = super().unlink()
        self.env["device.data.log.gps.report"]._rolling_mark_stale()
        return result

    def write(self, vals):
        result = super().write(vals)
        if {"resource_calendar_id", "company_id"} & vals.keys():
            self.env["device.data.log.gps.report"]._rolling_mark_stale()
        return result


class ResourceCalendar(models.Model):
    _inherit = "resource.calendar"

    def write(self, vals):
        result = super().write(vals)
        if "tz" in vals and self.env["resource.config"].sudo().search_count(
            [("resource_calendar_id", "in", self.ids)], limit=1
        ):
            self.env["device.data.log.gps.report"]._rolling_mark_stale()
        return result
