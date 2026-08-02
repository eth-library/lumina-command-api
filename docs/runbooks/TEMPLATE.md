# NN — Task name

**Audience:** who runs this (e.g. any team member with deploy rights)
**When:** the trigger for running it
**Duration:** rough wall-clock estimate
**Last verified:** YYYY-MM-DD — the last time someone ran these steps and they worked

## Prerequisites

- Tool, version, and how to check it is present
- Permission or role required
- State the system must be in before starting

## Variables

Set these once; every step below uses them.

```bash
export EXAMPLE_VAR="value"          # what it is, where to find it
```

## Steps

1. **What this step achieves.**
   ```bash
   command --flag "$EXAMPLE_VAR"
   ```
   Expected output: …

2. **Next step.**
   ```bash
   command
   ```

## Verification

How to know it worked — a command whose output you can check, not "confirm it looks right".

```bash
command
```

Expected: …

## Rollback

How to undo it. If it cannot be undone, say so explicitly and state what the recovery path is
instead.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| … | … | … |
