- smarter budget control

Let's implement smarter budget control:

- Instead of `generation_interval_seconds`, we have `weekly_budget_usd` (defaulting to 6)
- In `handle_message()`, instead of a fixed `interval = timedelta(seconds=SETTINGS.generation_interval_seconds)`, we use `timedelta(seconds=last_generation_cost_usd*seconds_per_week/weekly_budget_usd)`, where `last_generation_cost_usd` is `cost_usd` of the last (by `updated_at`) generation with a non-zero `cost_usd`, falling back to 0 if no such generation exists.
- As we currently don't have an `updated_at` field on `Generation`, we create this field. For existing generations, we set `updated_at` to `scheduled_for` (this won't be correct but will do for the sake of the algorithm). We do this in a data migration that should be stored in the same file as the auto-generated one. For new & pending generations, we set `updated_at` to `now()` when the generation is finished (either successfully or with an error, i.e. somewhere in a `finally` block).
- Let's also add notes in `README.md` and (a shorter one) in `CLAUDE.md` about this way of budget control as I think it's an important part of the project's technical architecture; clarify that it currently only works for the conversation agent, but is planned to be extended to the rationale agent as well once we unify the agents' APIs.

Clever?

- Auto-generate migrations with a sequentially-numbered version id right away
- Move profile field descriptions to schema instead of instructions
- Individual scheduling (if > X responses in Y minutes, schedule forward by Z minutes)
- Fix FULL resetting logic (including message sent) — needs some re-flowing
- Bug with thought bubble not disappearing on an error
- Enable cascade deletion (e.g. conversation -> generations, but also the rest)
