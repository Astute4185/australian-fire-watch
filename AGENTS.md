# Australian Fire Watch contributor guide

## Personal source and build route

Private VM300 hallyaus/australian-fire-watch is the primary source, Git SSH
port 2222. GitHub remains the public HACS download catalogue and identical
recovery copy with Actions disabled. Push completed source to VM300 first;
recovery pushes must not build or publish. Dedicated personal-ubuntu jobs
preserve Python units, actual HA runtime regressions, official hassfest,
JavaScript checks and deterministic private candidate packaging. An archive
is not a release: require exact-source official HACS validation before any
separately authorised publication. Never expose private primary source or
reuse M4T credentials. Existing shipped versions/assets stay immutable.

The official feed checker is manual-only until its first personal runner
execution passes. Then restore the existing weekly `17 3 * * 6` schedule;
perform read-only official-feed requests only, with no HA notifications or
household data. Do not classify an upstream contract failure as safe.

This repository is a HACS-installable Home Assistant integration for Australian
bushfire awareness. It is supplementary to official emergency channels and must
never describe missing or stale data as safe.

## Architecture

- `custom_components/australian_fire_watch/`: config flow, jurisdiction adapters,
  NSW RFS/BOM enrichment, normalized models, HA entities/events/services, and
  the bundled frontend.
- `custom_components/australian_fire_watch/frontend/`: prebuilt plain JavaScript loaded directly by Home Assistant; no runtime package manager.
- `blueprints/`: optional user-owned alert automations.
- `tests/`: deterministic unit tests. Keep feed parsing and ranking logic pure where possible.

## Safety rules

- Keep official warning level, incident control status, incident type, and proximity as separate fields.
- Unknown/unavailable/stale is never green and never “safe” or “all clear”.
- Reserve red for Emergency Warning or Catastrophic. Do not rely on colour alone.
- Use official source links and timestamps; expose stale age and retain the last good response.
- Do not infer fire spread, evacuation routes, or property safety.
- Notifications must be deduplicated by stable incident ID and lifecycle change; escalation always overrides snooze.
- Never commit Home Assistant `.storage`, coordinates, tokens, service names, or other household data.

## Release completion

When the owner requests a version bump or release, update both manifest.json
and const.py, validate the change, push main, publish the matching GitHub Release
and tag, and verify the release workflow and australian_fire_watch.zip asset.
A source version bump alone is not a completed HACS release. Do not overwrite
existing published release assets or move an existing tag.

## Validation

Run `python -m unittest discover -s tests -v`, compile Python, validate JSON/YAML, and run `ruff`/`mypy` when available. Production installation requires a Home Assistant configuration check before restart.

## Personal dependency review automation

The private VM300 dependency-updates workflow uses its short-lived, repository-only
Actions token to propose review PRs on renovate/personal-* branches. Only hallyaus
may push or merge main. Automatic merging, branch rebasing, install scripts, plugins
and post-upgrade commands are disabled. Existing application files and installed
versions are not changed by enrolling this route. Original validation gates run
against each exact proposal; an isolated job reports personal-dependency-checks.
The updater explicitly queues these checks because this Gitea version suppresses
bot-created PR events. Child runs must not be awaited inside the updater at shared
capacity one. Preserve existing proposals and inspect conflicts rather than
force-pushing. Retire the old GitHub updater only after this replacement is proved.
Private validation/package results do not authorize a public release, integration
installation, physical device/account action or a production application change.
