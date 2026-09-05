from dataclasses import dataclass

from app.auth.service import role_codes
from app.core.exceptions import PermissionDeniedError

VALUATION_ROLES = frozenset({"APPRAISER"})
REVIEW_ROLES = frozenset({"REVIEWER"})
FULL_ACCESS_ROLES = frozenset({"INSPECTOR", "ADMIN", "SYSTEM_ADMIN", "SUPERADMIN"})


@dataclass(frozen=True)
class HistoryScope:
    valuation: bool
    review: bool

    @property
    def modules(self) -> tuple[str, ...]:
        values = []
        if self.valuation:
            values.append("valuation")
        if self.review:
            values.append("review")
        return tuple(values)


def history_scope(user) -> HistoryScope:
    roles = role_codes(user)
    if roles & FULL_ACCESS_ROLES:
        return HistoryScope(valuation=True, review=True)
    scope = HistoryScope(
        valuation=bool(roles & VALUATION_ROLES),
        review=bool(roles & REVIEW_ROLES),
    )
    if not scope.modules:
        raise PermissionDeniedError("此角色不可調閱案件歷史")
    return scope
