# Contributing

Thanks for your interest. This project is a **template** — a skeleton people fork
and adapt — so contributions that keep it generic and well-documented are the most
valuable.

## Ground rules

1. **Keep the engine domain-agnostic.** `engine/` must not contain any subject
   matter. Domain logic belongs in `triage.yaml` and the `paths/` / `skills/`
   templates. PRs that hardcode a domain into the engine will be asked to move it
   to config. (See `AGENTS.md`.)
2. **Add mechanisms, not topics.** Good engine PRs add new *capabilities* (an
   embedding dedup backend, a new scoring mode, a new step type) — not new
   domains.
3. **Keep tests green.** `python -m unittest discover -s tests` must pass. Add
   tests for new mechanisms; cover them against a synthetic config like the
   existing ones.
4. **Validate config changes.** `python -m cli.triage validate` after any change
   to `triage.yaml` or the config schema.
5. **Never commit secrets or real data.** See `SECURITY.md` and `docs/06`.

## Dev setup

```bash
pip install -r requirements.txt
python -m unittest discover -s tests
python -m cli.triage validate
```

No build step; it's plain Python (3.10+) plus PyYAML.

## What's especially welcome

- New `examples/<domain>/` configs that show the engine fitting a different
  problem (GitHub issue triage, lead triage, support-ticket routing, …).
- Docs improvements — clearer adaptation guidance, more gotchas.
- An embedding-based dedup backend (the contract in `engine/dedup.py` is ready
  for it).
- A real `cli.triage scaffold`/`install` that drives a Hermes setup end to end.

## Style

Match the surrounding code: typed dataclasses, clear docstrings aimed at the
*adapting agent*, comments that explain *why*. Prefer stdlib; justify new
dependencies.
