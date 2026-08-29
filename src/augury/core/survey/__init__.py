"""Reading the deployment before reading the code.

A repository is a set of services, not a list of files. Which directory is the
backend, what it is written in, how many workers it runs and what it depends on
are all declared in the compose file, and reading that first is what turns a
flat ranking into a review with a scope.
"""

from augury.core.survey.model import BackingService, Service, Survey
from augury.core.survey.surveyor import Surveyor, entrypoint_refs

__all__ = ["BackingService", "Service", "Survey", "Surveyor", "entrypoint_refs"]
