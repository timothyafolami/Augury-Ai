"""The schema, read as one artefact rather than as many migration files.

A migration's defects are not in the file. `op.add_column(... nullable=False)`
is four correct lines that fail on any table with rows in it, and
`op.create_index` is one correct line that blocks every write to a table for as
long as the build takes. Neither is visible to a reviewer reading the file,
because the file is right; what is wrong is what the statement does to data
that already exists.

Everything here is deterministic. These are facts about DDL rather than
judgements, and a model asked to restate them would cost money to be right
slightly less often.
"""

from augury.core.schema.checks import schema_findings
from augury.core.schema.model import Operation, SchemaFinding
from augury.core.schema.reader import read_migrations

__all__ = ["Operation", "SchemaFinding", "read_migrations", "schema_findings"]
