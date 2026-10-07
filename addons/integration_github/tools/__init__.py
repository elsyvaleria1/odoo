from .app import InstallationToken, app_jwt, mint_installation_token
from .checks import ChecksMixin
from .client import GitHubClientBase
from .issues import IssuesMixin
from .records import create_once
from .repos import RepositoryMixin
from .repository import repository_domain, same_repository


class GitHubClient(GitHubClientBase, RepositoryMixin, IssuesMixin, ChecksMixin):
    pass


def get_github_client(env, company_id=None):
    return GitHubClient(env, company_id)


__all__ = [
    "GitHubClient",
    "InstallationToken",
    "app_jwt",
    "create_once",
    "get_github_client",
    "mint_installation_token",
    "repository_domain",
    "same_repository",
]
