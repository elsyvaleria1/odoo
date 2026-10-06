from . import models
from . import wizards


def uninstall_hook(env):
    access = env.ref("project.project_project_manager_rule", raise_if_not_found=False)
    if access and "database_hosting" in (access.domain or ""):
        access.write({"name": "Project: project manager: see all", "domain": False})
