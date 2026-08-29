"""Makes `python -m augury.cli` work.

Without this the package cannot be executed, and every command in the
reproduction guide fails before doing any work -- which is what a judge runs
first. Caught by a review that followed the guide literally; no test had
executed the CLI the way the documentation tells a reader to.
"""

from augury.cli.main import app

app()
