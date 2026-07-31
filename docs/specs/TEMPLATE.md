# NN — Module name

**Status:** Stub | Draft | Accepted | Implemented
**Date:** YYYY-MM-DD
**Author:** Name

## Goal

What the user achieves, in one or two sentences. Not what the code does — what becomes possible.

## User stories

- As a **role**, I want **capability**, so that **outcome**.
- As a **role**, I want **capability**, so that **outcome**.

Concrete and role-framed. "As a user I want the system to work" is not a user story.

## Acceptance criteria

Testable statements. Each one should be checkable by a person or a test without interpretation.

- [ ] Given **precondition**, when **action**, then **observable result**.
- [ ] Invalid input **X** is rejected with **status/message**.
- [ ] …

## API sketch

Endpoints, request and response shapes, status codes, and the data model. Enough that a client
developer could start work against it before the implementation exists.

```
POST /commands/example
  multipart/form-data
    file: <.csv | .csv.gz>
    option: string
  → 200 {"...": ...}
  → 400 {"detail": "..."}
```

## Out of scope

What this module deliberately does not do, so the boundary is explicit.
