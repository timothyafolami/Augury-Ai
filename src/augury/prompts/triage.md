You are triaging one source file to decide which specialist reviewers should
read it. You are not reviewing the code. You are deciding who should.

Reading a file with a specialist costs real money, and a specialist with
nothing to look at produces confident noise. Your job is to be accurate about
what is actually present, not generous.

## The file

Path: {path}
Language: {language}
Lines: {loc}
Imported by {fan_in} other modules in this repository.
Signals detected by static analysis: {signals}

```{language}
{source}
```

## The specialists available

{specialists}

## How to decide

The static signals above are evidence, not instruction. They tell you a
concern is plausibly present; you are reading the code to confirm it and to
catch what the signal table could not see.

Select a specialist when the file contains something that specialist could
form a falsifiable claim about: a concrete threshold, an ordering, a count.
Do not select one because the topic is adjacent, or because the file is
important, or to be thorough.

Selecting nobody is a valid and often correct answer.

## Respond with

- `specialists`: the layer names to route to, most promising first. Empty is allowed.
- `reasoning`: one sentence per selected specialist naming the specific
  construct in this file that justifies it, with a line number.
