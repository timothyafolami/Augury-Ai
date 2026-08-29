You are routing one source file to the specialists who should read it.

You are **not** deciding whether this file has a bug. You are deciding who is
qualified to look. Those are different questions, and answering the first one
here is the most expensive mistake available: a specialist you do not call
cannot find anything, and nothing downstream can recover the miss.

So the test for including a specialist is **presence, not certainty**. If the
file touches that specialist's concern at all, include it. The specialist will
read the code properly, with the reference material for its layer, and will
report nothing if there is nothing. Let it.

Exclude a specialist only when its concern is genuinely absent from the file:
no concurrency specialist for a module with no shared state and no tasks, no
data specialist for a module that never touches a query or a session.

Choose nobody only for a file with nothing to review at all: constants, pure
type declarations, generated code, a list of strings.

## How this service is deployed

{context}

## The file

Path: {path}
Language: {language}
Lines: {loc}
Imported by {fan_in} other modules in this repository.
Concerns detected by static analysis: {signals}

```{language}
{source}
```

## The specialists available

{specialists}

## Respond with

- `specialists`: the layer names that should read this file, most promising
  first. Only names from the list above.
- `reasoning`: one short sentence per selected specialist naming what in this
  file is theirs to review.
