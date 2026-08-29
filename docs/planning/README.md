# Written before the build

These three documents were written in the first hours of the competition, and
they describe a product that was not built.

`PRD.md` specifies a runtime incident-diagnosis agent called Differential,
operating on a live docker-compose stack with twelve injected faults, an MCP
server, a VS Code extension and an L0-L4 rung ladder. `BUILD_PLAN.md` plans
that architecture. `DEFECT_TAXONOMY.md` catalogues fifteen defects across three
repositories that do not exist under those names.

They are kept because the competition asks for the reasoning, and because the
distance between them and what shipped is the most honest thing in the
repository. Nothing in them should be read as a description of this codebase.

**What actually exists** is recorded in:

| | |
|---|---|
| [`../CHANGELOG.md`](../CHANGELOG.md) | Twenty-two iterations, each with the run that caused it |
| [`../../README.md`](../../README.md) | What was built and what it measured |
| `eval/cases/*/case.json` | The real defect taxonomy: every seeded defect, its lab topic, its locations and the experiment that settles it |

The last of those is the traceability artefact. Every case manifest carries a
required `lab_topic`, and a test refuses a case without one.
