from odoo import api, models


class ProjectCollaborator(models.Model):
    _inherit = "project.collaborator"

    @api.model_create_multi
    def create(self, vals_list):
        collaborators = super().create(vals_list)
        collaborators.project_id._sync_document_audience()
        return collaborators

    def write(self, vals):
        projects = self.project_id
        result = super().write(vals)
        (projects | self.project_id)._sync_document_audience()
        return result

    def unlink(self):
        projects = self.project_id
        result = super().unlink()
        projects._sync_document_audience()
        return result
