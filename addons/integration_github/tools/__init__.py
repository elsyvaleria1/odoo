from .client import GitHubClientBase
from .repos import RepositoryMixin
from .issues import IssuesMixin


class GitHubClient(GitHubClientBase, RepositoryMixin, IssuesMixin):
    pass


def get_github_client(env, company_id=None):
    return GitHubClient(env, company_id)


__all__ = ["GitHubClient", "get_github_client"]
