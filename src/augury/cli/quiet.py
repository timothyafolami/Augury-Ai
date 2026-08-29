"""Silencing one warning from a dependency, and only that one.

Every model call printed nine lines of this:

    UserWarning: Pydantic serializer warnings:
      PydanticSerializationUnexpectedValue(Expected `none` - serialized value
      may not be as expected [field_name='parsed', ...])

autogen logs the OpenAI SDK's response object, whose `parsed` field is
declared as None and holds a parsed model. Nothing here can change that
object, and on a hundred-module run it buries the review under several hundred
lines about a field this project never declared.
"""

from __future__ import annotations

import warnings

# Narrow on purpose. A serializer warning about one of our own fields means a
# model is being written wrongly, and that is worth reading.
# `(?s)` because the warning is multi-line and the field name is on the second
# one; warnings.filterwarnings anchors its pattern at the start of the message.
_FROM_THE_SDK = r"(?s).*field_name='parsed'.*"


def quiet_dependency_noise() -> None:
    """Hide the OpenAI SDK's `parsed` serializer warning. Nothing else."""
    warnings.filterwarnings(
        "ignore",
        message=_FROM_THE_SDK,
        category=UserWarning,
    )
