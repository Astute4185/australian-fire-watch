# Personal Gitea validation and HACS compatibility

VM300 is the private source of truth. The original public GitHub repository,
tags and release ZIPs continue serving installed HACS users. GitHub Actions
remain disabled; routine recovery pushes cannot execute their workflows.

The new personal runner route retains the original Python3.13 unit/packaging
tests and undefined-name checks, Python3.14 actual Home Assistant runtime
suite, official hassfest, Node24 JavaScript syntax and frontend regressions.
Jobs use immutable official image digests and exact VM300 source. They use no
live account, Home Assistant instance, notification service, Docker socket or
privileged mode. First full runner execution is pending.

The candidate ZIP preserves the existing HACS root layout. It contains only
regular tracked integration blobs, with deterministic POSIX member paths,
permissions and timestamps. Version equality, clean source, preceding gates
and archive round-trip are enforced. A receipt records the exact source/run
and checksum. The pinned v3 upload action retains this candidate on private
Gitea; no tag or public release is created.

Official HACS validates public GitHub contents and requires its own read-only
GitHub credential. It cannot use a Gitea job token. Until the official HACS
gate passes for the identical recovery SHA, candidates are not release-ready.
Use repository-only credentials; never extract local CLI auth or reuse M4T
credentials. Published assets/tags must never be overwritten or moved.

For an authorised future product release, first validate the exact source and
candidate; push identical recovery; complete HACS; verify manifest/constant
versions and immutable tags on both remotes; create a draft with the already
verified ZIP using normal personal CLI authentication; download and compare
its checksum/members before publishing the same draft. This migration does
not request a new version or change the current release.

`official-feeds.yml` preserves the bounded read-only publisher contract check.
It starts manual-only. After its first successful run, restore the existing
weekly Saturday03:17UTC schedule. A failed feed contract remains visible and
must not generate a healthy/green status. No live HA restart or installation
is part of migration; those require the existing configuration check first.

The first runner unit job451 passed91of92checks; the existing private-state
packaging guard correctly rejected the new literal LAN source address in CI
metadata. That guard is unchanged. The expected primary URL now lives only in
the repository-level non-secret `PERSONAL_GITEA_SERVER` Actions variable, using
the supported Gitea `vars` context. Every checkout still refuses an absent or
different expected server, repository, branch or source SHA. Private candidate
provenance records the checked runtime URL rather than embedding it in public
source. No feed, notification, entity, product version or published asset changed.
The corrected full runner route remains unverified until all gates complete.

Variable support: https://docs.gitea.com/usage/actions/actions-variables/
