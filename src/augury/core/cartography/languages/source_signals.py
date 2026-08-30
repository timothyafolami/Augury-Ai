"""What a file says about itself, in languages that are not Python.

Signals were derived from imports alone outside Python, so a swallowed error
in Go, TypeScript, Java, Rust or C++ raised nothing, and a query built by
interpolation raised nothing. Those are the two highest-value detectors in the
project and they existed for one of six languages.

Read as text rather than as a tree. Tree-sitter is already parsing these files
for their imports, but a query per construct per grammar is a great deal of
surface for two rules, and the rules are lexical: what makes a catch block a
swallowed error is the absence of a throw inside it, and what makes a query
injectable is a keyword next to an interpolation.

A false positive is worse than a miss here. It routes a specialist to a file
with nothing to say, and a specialist with nothing to say invents something.
So each pattern is written to the narrowest thing that is still true, and the
negative cases are as much the specification as the positive ones.
"""

from __future__ import annotations

import re

from augury.core.cartography.model import Signal

# The statement keywords. A file merely mentioning the word "select" in prose
# is not a query, so a keyword only counts when it opens a statement.
_SQL = re.compile(
    r"\b(?:select\s+.+?\s+from|insert\s+into|update\s+\w+\s+set|delete\s+from)\b",
    re.IGNORECASE | re.DOTALL,
)

# Building a string from a value, per language. Each is the construct that
# concatenates, never merely the presence of a variable.
_WOVEN = re.compile(
    r"""(
        \$\{                      # a template literal, TypeScript and JavaScript
        | \{\}                    # a format! placeholder, Rust
        | %[sdv]                  # Sprintf and String.format, Go and Java
        | ["'`]\s*\+              # a literal joined to something, any quote
        | \+\s*["'`]              # or something joined to a literal
        | \)\s*\+                 # or a wrapped literal joined to one, C++
    )""",
    re.VERBOSE,
)

# Two string literals joined to each other, which is how a long statement is
# wrapped rather than how a value is woven in. Collapsed before the
# interpolation test, because `"SELECT * FROM t " + "WHERE id = ?"` otherwise
# matches the quote-then-plus shape and a correctly-bound query is reported as
# injection.
#
# This replaced a `_BOUND` pattern that looked for placeholders and was never
# wired to anything. Suppressing on a placeholder would also have been wrong:
# a query can bind one parameter and interpolate another, and that is a real
# defect rather than an excused one.
_LITERAL_JOIN = re.compile(r"""(['"])\s*\+\s*(['"])""")

# Rust hands the caller a panic instead of the error. The failure does not stop
# propagating so much as stop being a value anybody can handle.
_RUST_PANICS = re.compile(r"\.\s*(?:unwrap|expect)\s*\(")

# A Go assignment that throws a value away. The blank identifier is also the
# idiom for an unused loop variable, which is not an error being dropped.
_GO_DISCARD = re.compile(r"^\s*(?![^=\n]*\brange\b)([\w,\s_]*\b_\b[\w,\s_]*)\s*:?=", re.MULTILINE)

_CATCH = re.compile(r"\bcatch\s*\(([^)]*)\)\s*\{", re.IGNORECASE)

# What makes a catch broad. A narrow catch returning a default is a decision
# about one named failure; a broad one returning a default is every failure,
# including the ones nobody thought about, becoming a plausible empty answer.
# JavaScript and TypeScript cannot narrow a catch at all, so every catch there
# is this.
_BROAD = re.compile(r"\b(?:Exception|Throwable|RuntimeException|Error|std::exception)\b")
_UNTYPED = ("typescript", "javascript", "tsx")

# Node runs one thread. A synchronous call does not slow the request that made
# it; it stops every other request in the process, health checks included.
#
# Named rather than matched on the `Sync` suffix. The suffix is the convention
# the standard library follows, but user code follows it too -- a factory
# called `makeSync` is an ordinary name, and routing every file containing one
# to the concurrency specialist spends a model call to be told nothing. These
# are the calls that actually hold the loop: filesystem, subprocess, crypto
# key derivation and compression, which is where the time goes.
_BLOCKING_CALLS = (
    # node:fs
    "readFileSync",
    "writeFileSync",
    "appendFileSync",
    "readdirSync",
    "statSync",
    "existsSync",
    "unlinkSync",
    "mkdirSync",
    "copyFileSync",
    # node:child_process
    "execSync",
    "execFileSync",
    "spawnSync",
    # node:crypto -- the expensive ones by design
    "pbkdf2Sync",
    "scryptSync",
    "generateKeyPairSync",
    # node:zlib
    "gzipSync",
    "gunzipSync",
    "deflateSync",
    "inflateSync",
    "brotliCompressSync",
)
_BLOCKS_THE_LOOP = re.compile(r"\b(?:" + "|".join(_BLOCKING_CALLS) + r")\s*\(")

# Where one thread serves every request, so a blocking call is everyone's
# problem. A Go function spelled the same way blocks one goroutine and the
# scheduler runs the rest, which is why this is scoped rather than global.
_SINGLE_THREADED = ("typescript", "javascript", "tsx")

# The network call these runtimes make has no import behind it. `fetch` is a
# global, and so are the streaming transports, so a signal table keyed on
# imports is blind to the most common outbound call in the language.
#
# Anchored so that `repo.fetch(id)` and `this.fetch()` stay ordinary names: a
# member call is somebody's data-access method far more often than it is the
# global, and routing every repository class to the network specialist buys
# nothing. `new` is required for the constructors for the same reason.
_GLOBAL_NETWORK = re.compile(
    r"(?<![.\w])fetch\s*\(|\bnew\s+(?:WebSocket|EventSource)\s*\(|\bnavigator\.sendBeacon\s*\("
)


def signals_in_source(language: str, text: str) -> frozenset[Signal]:
    """The concerns this file raises by what it does, not by what it imports."""
    found: set[Signal] = set()

    if _swallows_an_error(language, text):
        found.add(Signal.CRAFT)

    if _weaves_a_query(text):
        found.add(Signal.SECURITY)
        found.add(Signal.DATA)

    if _blocks_the_only_thread(language, text):
        found.add(Signal.CONCURRENCY)

    if _calls_the_network_without_importing(language, text):
        found.add(Signal.NETWORK)

    return frozenset(found)


def _calls_the_network_without_importing(language: str, text: str) -> bool:
    """An outbound call made through a global rather than a dependency."""
    if language not in _SINGLE_THREADED:
        return False
    return _GLOBAL_NETWORK.search(_without_comments(text)) is not None


def _without_comments(text: str) -> str:
    """Prose describing a call is not a call.

    Only line comments are stripped, which is what the false positive was:
    "// fetch the row" in a file that never touches the network.
    """
    return "\n".join(line.split("//", 1)[0] for line in text.splitlines())


def _blocks_the_only_thread(language: str, text: str) -> bool:
    """A synchronous standard-library call on a runtime with one thread."""
    if language not in _SINGLE_THREADED:
        return False
    return _BLOCKS_THE_LOOP.search(text) is not None


def _swallows_an_error(language: str, text: str) -> bool:
    """Whether a failure here stops propagating and nobody is told."""
    if language == "rust":
        return bool(_RUST_PANICS.search(text))

    if language == "go":
        return any(_drops_an_error(line) for line in _GO_DISCARD.findall(text))

    # Java, TypeScript, JavaScript, C++: a broad catch whose body never
    # rethrows. Narrowness is the whole distinction, so it is checked first.
    for caught, span in _catch_bodies(text):
        if not _is_broad(language, caught):
            continue
        if _body_never_rethrows(text, span):
            return True
    return False


def _is_broad(language: str, caught: str) -> bool:
    """Whether this catch takes everything rather than one named failure."""
    if language in _UNTYPED:
        # `catch (err)` cannot be narrowed. Every catch in these languages
        # takes everything, so the type says nothing and the body decides.
        return True
    if "..." in caught:
        return True  # C++ catch-all
    return bool(_BROAD.search(caught))


def _drops_an_error(targets: str) -> bool:
    """Whether this assignment throws the error away rather than a value.

    `_, err := read()` keeps the error and is correct. `n, _ := Atoi(raw)`
    drops it. The difference is whether anything error-shaped is still bound,
    so the name is what decides it, which is exactly how a Go reviewer decides
    it too.
    """
    names = [name.strip() for name in targets.split(",")]
    if "_" not in names:
        return False
    return not any(name.lower().startswith("err") for name in names if name != "_")


def _catch_bodies(text: str) -> list[tuple[str, tuple[int, int]]]:
    """What each catch takes, and where its body begins and ends."""
    spans: list[tuple[str, tuple[int, int]]] = []
    for match in _CATCH.finditer(text):
        opened = match.end() - 1
        depth = 0
        for index in range(opened, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    spans.append((match.group(1), (opened + 1, index)))
                    break
    return spans


def _body_never_rethrows(text: str, span: tuple[int, int]) -> bool:
    """A catch that neither rethrows nor raises anything of its own.

    Logging is not enough on its own and is not checked for: a handler that
    logs and returns an empty list is the defect this rule is named after,
    because the caller cannot tell the empty answer from a real one.
    """
    body = text[span[0] : span[1]]
    return "throw" not in body and "rethrow" not in body


def _weaves_a_query(text: str) -> bool:
    """Whether a statement is built by joining a value into it.

    Both halves are required. A parameterised query mentioning SELECT is
    correct, and a comment mentioning SELECT is not a query at all, so the
    keyword alone proves nothing and the interpolation alone proves nothing.

    Literal-to-literal joins are collapsed first. Wrapping a long statement
    across two strings is formatting; joining a value between them is the
    defect, and the quote-then-plus shape cannot tell them apart on its own.
    """
    for line in _statements(text):
        if not _SQL.search(line):
            continue
        if _WOVEN.search(_without_literal_joins(line)):
            return True
    return False


def _without_literal_joins(line: str) -> str:
    """The line with literal-to-literal concatenation collapsed away.

    Applied repeatedly, because three literals joined in a row collapse one
    pair at a time and a single pass would leave the last join standing.
    """
    previous = ""
    while previous != line:
        previous = line
        line = _LITERAL_JOIN.sub("", line)
    return line


def _statements(text: str) -> list[str]:
    """Lines, joined across a wrapped statement.

    A query is routinely written over several lines with the interpolation on
    one of them and the keyword on another, and reading line by line finds
    neither.
    """
    joined: list[str] = []
    buffer = ""
    for line in text.splitlines():
        buffer = f"{buffer} {line.strip()}" if buffer else line.strip()
        if line.rstrip().endswith((";", ")", "`", '"', "'", "}")):
            joined.append(buffer)
            buffer = ""
    if buffer:
        joined.append(buffer)
    return joined
