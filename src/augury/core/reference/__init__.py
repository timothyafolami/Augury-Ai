"""What the ecosystem currently ships, against what the repository pins.

A model's knowledge of a library ends at its training cutoff, and the defaults
it remembers may not be the defaults installed. The registry is the authority
on that, it is free, and it needs no key -- so the gap between a pin and what
is current is a fact rather than a recollection.

The gap is worth reporting on its own. A service pinned three majors behind the
library whose defaults it relies on is a finding, and no amount of reading the
source produces it.
"""

from augury.core.reference.registry import PackageFacts, Registry
from augury.core.reference.requirements import requirements_of

__all__ = ["PackageFacts", "Registry", "requirements_of"]
