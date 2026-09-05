from types import SimpleNamespace

import pytest

from app.core.exceptions import PermissionDeniedError
from app.history.permissions import history_scope


def user(*roles):
    return SimpleNamespace(
        roles=[SimpleNamespace(role_code=role, is_active=True) for role in roles]
    )


@pytest.mark.parametrize("role", ["INSPECTOR", "ADMIN", "SYSTEM_ADMIN", "SUPERADMIN"])
def test_privileged_roles_can_read_both_modules(role):
    scope = history_scope(user(role))
    assert scope.valuation is True
    assert scope.review is True


def test_combined_appraiser_and_reviewer_can_read_both_modules():
    scope = history_scope(user("APPRAISER", "REVIEWER"))
    assert scope.modules == ("valuation", "review")


def test_single_roles_are_isolated():
    assert history_scope(user("APPRAISER")).modules == ("valuation",)
    assert history_scope(user("REVIEWER")).modules == ("review",)


def test_unknown_role_is_denied():
    with pytest.raises(PermissionDeniedError):
        history_scope(user("GUEST"))
