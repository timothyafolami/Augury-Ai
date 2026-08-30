"""Opting out of a language's safety guarantee is a security concern.

Each of these languages offers a guarantee and a way to switch it off. Rust
checks bounds and aliasing until an `unsafe` block says not to. C++ offers
bounded string handling and also ships `strcpy`, which does not know how big
the destination is. Java runs in a sandbox and also ships
`Runtime.exec` and `ObjectInputStream.readObject`, which are the two most
reliable ways out of it.

None of them import anything that says so. `unsafe` is a keyword, `strcpy`
comes from a header the file already needed, and `Runtime` is in
`java.lang`, which is imported implicitly and therefore appears in no import
list anywhere.

So the signal that routes a file to the security specialist could not be
raised by the constructs that most deserve it. Measured across nine probes,
all nine raised nothing at all.

The practice lab names these: `01-machine/04-races-and-atomicity` on what the
type system refuses to let you write and what `unsafe` makes visible, and
Layer 7 throughout on the ways a process is convinced to run someone else's
instructions.
"""

from __future__ import annotations

import pytest

from augury.core.cartography.languages.source_signals import signals_in_source
from augury.core.cartography.model import Signal

DEFEATED = [
    ("rust", "unsafe { *ptr = 5; }", "an unsafe block"),
    ("rust", "let f = std::mem::transmute::<u64, f64>(bits);", "transmute"),
    ("rust", "let v = data.get_unchecked(index);", "an unchecked index"),
    ("rust", "let s = String::from_utf8_unchecked(bytes);", "unchecked utf8"),
    ("cpp", "char dst[64];\nstrcpy(dst, src);", "strcpy into a fixed buffer"),
    ("cpp", "strcat(path, suffix);", "strcat"),
    ("cpp", 'sprintf(buf, "%s", name);', "sprintf"),
    ("cpp", "gets(line);", "gets"),
    ("java", "Runtime.getRuntime().exec(command);", "command execution"),
    ("java", "new ProcessBuilder(argv).start();", "process builder"),
    ("java", "Object o = new ObjectInputStream(in).readObject();", "java deserialisation"),
]

ORDINARY = [
    ("rust", "// unsafe code was removed in this refactor", "the word in a comment"),
    ("rust", "let unsafely_named = 1;", "an identifier containing the word"),
    ("cpp", "// sprintf was replaced with std::format here", "a comment about it"),
    ("cpp", "std::string joined = a + b;", "safe string handling"),
    ("java", "executor.execute(task);", "an unrelated execute"),
    ("java", "int safety = 1;", "an ordinary variable"),
    ("go", "unsafe.Pointer(&x)", "go, which is not covered by this rule"),
    ("python", "unsafe = True", "python, which has its own detector"),
]


@pytest.mark.parametrize("language,source,why", DEFEATED, ids=[f"{a}-{c}" for a, _, c in DEFEATED])
def test_defeating_the_guarantee_raises_security(language: str, source: str, why: str) -> None:
    assert Signal.SECURITY in signals_in_source(language, source), (
        f"{why}: this is where the language stops protecting the caller"
    )


@pytest.mark.parametrize("language,source,why", ORDINARY, ids=[f"{a}-{c}" for a, _, c in ORDINARY])
def test_ordinary_code_raises_nothing(language: str, source: str, why: str) -> None:
    """Routing a file to a specialist costs a model call, so a rule that fires
    on a word in a comment spends money to be told nothing."""
    assert Signal.SECURITY not in signals_in_source(language, source), why


def test_an_unsafe_block_is_not_confused_with_a_safe_one() -> None:
    """Rust's own vocabulary uses the word both ways, and only one is a
    concern: `unsafe fn` and `unsafe {` opt out, `safe` does not."""
    assert Signal.SECURITY in signals_in_source("rust", "unsafe fn raw(p: *mut u8) {}")
    assert Signal.SECURITY not in signals_in_source("rust", "fn safety_check(v: &[u8]) {}")
