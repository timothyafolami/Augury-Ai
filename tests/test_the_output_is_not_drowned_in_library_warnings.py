"""Every model call printed a nine-line Pydantic warning from a dependency.

    UserWarning: Pydantic serializer warnings:
      PydanticSerializationUnexpectedValue(Expected `none` ... field_name='parsed' ...)

It comes from autogen logging an OpenAI SDK response object whose `parsed`
field is declared None and holds a parsed model. Nothing in this project can
change that object, and on a run of a hundred modules it buries the review
under several hundred lines of traceback about a field nobody here declared.

Suppressing warnings wholesale would hide our own, so this suppresses exactly
that one and proves it still lets ours through.
"""

from __future__ import annotations

import warnings

from augury.cli.quiet import quiet_dependency_noise


def test_the_serializer_warning_from_the_dependency_is_suppressed() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        quiet_dependency_noise()
        warnings.warn(
            "Pydantic serializer warnings:\n"
            "  PydanticSerializationUnexpectedValue(Expected `none` - serialized value "
            "may not be as expected [field_name='parsed', input_value=DraftReport()])",
            UserWarning,
            stacklevel=1,
        )

    assert caught == []


def test_our_own_warnings_still_reach_the_reader() -> None:
    """A filter that hides everything hides the thing worth reading."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        quiet_dependency_noise()
        warnings.warn("the cache directory is not writable", UserWarning, stacklevel=1)

    assert len(caught) == 1


def test_another_pydantic_warning_about_a_different_field_is_not_hidden() -> None:
    """Narrow on purpose: a serializer warning about our own model is a bug."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        quiet_dependency_noise()
        warnings.warn(
            "Pydantic serializer warnings:\n"
            "  PydanticSerializationUnexpectedValue(field_name='severity')",
            UserWarning,
            stacklevel=1,
        )

    assert len(caught) == 1
