from .app import InstallationToken, app_jwt, mint_installation_token
from .checks import ChecksMixin
from .client import GitHubClientBase
from .issues import IssuesMixin
from .repos import RepositoryMixin


class GitHubClient(GitHubClientBase, RepositoryMixin, IssuesMixin, ChecksMixin):
    pass


def get_github_client(env, company_id=None):
    return GitHubClient(env, company_id)


__all__ = [
    "GitHubClient",
    "InstallationToken",
    "app_jwt",
    "get_github_client",
    "mint_installation_token",
]
