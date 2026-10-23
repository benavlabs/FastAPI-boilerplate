"""Reading which constraint refused a row, which decides what a collision answers."""

import re

from sqlalchemy.exc import IntegrityError

NAMED_CONSTRAINT = re.compile(r'constraint "([^"]+)"')
"""What a refusal quotes the constraint as, where the driver's own name for it is missing."""


def refused_constraint(collision: IntegrityError) -> str:
    """The constraint a refusal names, or ``""`` where nothing in it names one.

    asyncpg names the constraint on the error the driver wrapped, which the dialect keeps
    as the cause; the message is read only where that is missing, and read for the name it
    quotes rather than searched for one. Either way the name is matched whole, so a later
    constraint called something like ``ix_user_email_of_whatever`` is nobody else's.
    """
    named = getattr(getattr(collision.orig, "__cause__", None), "constraint_name", None)
    if named:
        return str(named)

    quoted = NAMED_CONSTRAINT.search(str(collision.orig))

    return quoted.group(1) if quoted else ""
