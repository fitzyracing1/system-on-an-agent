# Add-on interface

The core of a System on an Agent is only the planner, memory and skills, connectors, and the bus. Add-ons sit beside that core. They never live inside it, and loading or omitting them does not require a core change.

## Manifest

Every add-on exposes an `AddonManifest`:

- `name` — stable identifier
- `version` — add-on version string
- `description` — short summary
- `hooks` — the hook names this add-on implements
- `author` — optional

Known hooks:

| Hook | Signature | Role |
| --- | --- | --- |
| `before_plan` | `(plan, context) -> plan` | Inspect or replace the plan |
| `after_plan` | `(plan, report, context) -> report` | Inspect or replace the run report |
| `before_step` | `(step, context) -> step` | Inspect or replace a step before it runs |
| `after_step` | `(step, result, context) -> result` | Inspect or replace a step result |
| `on_error` | `(step, error, context) -> None` | Observe a failed step |

Returning `None` leaves the current value unchanged. `context` is a `HookContext` with the original `goal` and an `extras` dict for add-on state.

Returning anything else the core cannot use (for example a plain dict from `before_step`) raises `AddonError` naming the add-on, instead of failing later inside the core.

## Loading

An add-on is a Python file, or a directory containing `soa_addon.py` or `addon.py`. The module must define one of:

- `create_addon()` — a factory
- `Addon` — a class with a no-argument constructor
- `addon` — a ready-made instance

```bash
soa --addon path/to/addon.py run "echo hello"
```

Two add-ons declaring the same manifest `name` are rejected (`add-on already loaded`) unless the loader is called with `overwrite=True`.

Entry points in the `soa.addons` group are also reserved for later discovery; none ship with the core.

## Future add-ons (placeholders only)

These names are reserved so later work can plug in without a core redesign. **There is no implementation and no dependency for either one in this repository.**

### heatgate

Power throttling from measured temperature and grid readings. A future heatgate add-on would hook `before_step` to pause, delay, or skip work when those readings are high, and `after_step` to record what was throttled. It would be an optional power-management add-on, not part of the processor, storage, or I/O of the agent itself.

### lex-loop

An 8-step robot loop (READ → RESTART) used as a clock. A future lex-loop add-on would hook plan execution so each tick advances one phase of that loop. It would be an optional clock add-on, not part of the core planner.

Do not import, install, or vendor either add-on into the core.
