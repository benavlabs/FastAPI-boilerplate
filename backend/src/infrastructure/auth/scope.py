"""Whether a credential narrows what its account holds."""

from crudauth import Principal

SCOPE_OWNER_IS_SUPERUSER = "scope_owner_is_superuser"
"""Metadata a scoped transport records: the superuser flag of the account behind it.

Its presence is what marks a credential as scoped, so the transport that narrows is the
one that declares it.
"""


def carries_a_scope(principal: Principal) -> bool:
    """Whether ``principal`` came from a credential that carries a scope.

    Such a principal holds its owner's permissions narrowed to ``principal.scopes``, and
    its ``is_superuser`` is false whatever the account is marked, so no consumer has to
    remember: the flag reaches ownership checks a scope cannot express.
    """
    return SCOPE_OWNER_IS_SUPERUSER in principal.metadata


def owner_is_superuser(principal: Principal) -> bool:
    """Whether the account behind a scoped credential holds the superuser flag.

    Only the narrowing reads it: a superuser's permissions are every registered one, which
    a scope narrows like any other set.
    """
    return bool(principal.metadata.get(SCOPE_OWNER_IS_SUPERUSER))
