# Slice 2 branch topology and consolidation plan

## Historical pre-merge audit

Audit basis: local and remote refs inspected on 2026-09-22 at the pre-task tip
`00fcabf7f01557fb81b3aafdf04711aff13d2e48`. The candidate then added only the
bounded commits reported in the final handoff. The topology and proposed actions
below are the historical pre-merge snapshot; they do not describe the current live
refs.

## Historical repository topology

At audit time, the remote was `origin` (`https://github.com/duck-lint/normalize`).
Its advertised HEAD and the local default-tracking branch were `origin/guh`;
local `guh` was at `a2ccdb1f06f3e97fbcc437fb969636305031355f`.
`origin/master` was an older ancestor, not the remote default. The remote
`origin/slice2/geometry-probe-checkpoint` ref was stale according to
`git remote show origin` and was also an ancestor of `origin/guh`.

All six published research tips form a linear descendant stack from `guh` and
are ancestors of the current candidate. Each has zero commits unique relative
to the current candidate; its listed tip commit is the incremental research
commit at that stage.

| Ref | Tip SHA | Remote/upstream | Relation to candidate | Unique work | Historical proposed action | Final disposition |
| --- | --- | --- | --- | --- | --- | --- |
| `guh` / `origin/guh` | `a2ccdb1f06f3e97fbcc437fb969636305031355f` | tracked; default | ancestor, merge base | base Slice 2 history | destination; do not alter in this task | retained as the default integration branch |
| `geometry-forensics-identity-oracle` / origin | `6453d2890fce5799640d7219effdd090ea6aed2d` | tracked, up to date | ancestor; +1 from default | residual evidence and identity oracle | archive after integration approval | retired locally and remotely after merge |
| `diagnostic-investigation-sparse-vertical` / origin | `d2dbea8e8e1a51ad92b38bb2caddb7f209542e72` | tracked, up to date | ancestor; +2 | sparse/vertical diagnostics | archive after integration approval | retired locally and remotely after merge |
| `evidence-corrections-pixel-experiments` / origin | `699771d01c1a83c6f89c6a7eb2102e79a709b671` | tracked, up to date | ancestor; +3 | evidence corrections and errata | archive after integration approval | retired locally and remotely after merge |
| `pixel-evidence-prototype` / origin | `c0f7ea88493a07e6139e9c71d413a2eda130c17b` | tracked, up to date | ancestor; +4 | research pixel measurements | archive after integration approval | retired locally and remotely after merge |
| `vertical-clustering-investigation` / origin | `dfa6cd1ef2387364dded5ba86f92635d94875b4d` | tracked, up to date | ancestor; +5 | non-greedy comparison | archive after integration approval | retired locally and remotely after merge |
| `verification-repair-stage-ablation` / origin | `00fcabf7f01557fb81b3aafdf04711aff13d2e48` | tracked, up to date | parent of candidate; +6 | verification repair and stage ablation | retain until candidate is accepted; then archive | retired locally and remotely after merge |
| `verification-reconciliation-slice2-decision` | `00fcabf7f01557fb81b3aafdf04711aff13d2e48` | no upstream; current worktree | candidate; +6 from default at audit | this reconciliation, tests, and records | proposed PR source | final tip was `9867a0d0f19d22cc9f102f6c94cd2c2c58cd0fed`; merged into `guh`, then retired locally and remotely |
| `origin/master` | `93c6ef1ead9fd30aaf94b210a79aa2c6a39a16ff` | remote only | ancestor of default; not destination | older default line | retain unless repository owner changes policy | retained; not part of the cleanup |
| `origin/slice2/geometry-probe-checkpoint` | `4998f8c9d2a40bf6e9b62d04ec916ca382ea693c` | remote stale ref | ancestor of default; +4 behind default | historical checkpoint | do not prune without owner approval | no longer advertised after later fetch/prune; not part of the research-ref retirement |

There is one worktree, at the repository path, currently associated with the
candidate branch. At audit time the only uncommitted state was the intended
verification test edit; no other branch has a worktree-associated change.
The published refs themselves are clean immutable pointers.

## Historical consolidation sequence (completed)

This is the sequence as planned during the audit. The later execution and final
topology are recorded in the post-merge disposition below.

1. Review this candidate's diff, focused tests, full suite, protected-file
   hashes, and documentation. No branch operation is implied by this record.
2. With explicit maintainer approval, open a pull request from
   `verification-reconciliation-slice2-decision` to `origin/guh`. Preconditions
   are a clean candidate worktree, green tests, valid research hashes, and no
   changes to production geometry, fixture contracts, oracle, source inputs, or
   SYMPHONY.
3. Merge the approved PR into the default branch using the repository's normal
   non-force integration policy. If `guh` advances or diverges, stop and
   re-audit ancestry rather than silently rebasing or rewriting history.
4. Verify the merged tree and evidence hashes on the default branch. Only then,
   with separate approval, delete obsolete local or remote research branch
   refs whose commits and artifacts are reachable from the accepted destination.
5. Treat the stale `origin/slice2/geometry-probe-checkpoint` ref separately;
   prune it only after its owner confirms that no external workflow depends on
   the historical pointer. `origin/master` is also a policy decision, not an
   inferred cleanup target.

The only approval-dependent actions were PR creation if repository policy
required it, merging, and any local/remote branch deletion or stale-ref prune.
At the time of audit, none of those actions had been performed; they were later
completed as recorded below.

## Post-merge disposition

The final consolidation branch tip was
`9867a0d0f19d22cc9f102f6c94cd2c2c58cd0fed`. That branch was merged into the
default branch `guh`, whose verified `guh` and `origin/guh` tip at reconciliation
was `adebafcd75090b301e5902c20cb071240671ef05`.

The following obsolete local and remote research refs were subsequently retired:

- `geometry-forensics-identity-oracle`
- `diagnostic-investigation-sparse-vertical`
- `evidence-corrections-pixel-experiments`
- `pixel-evidence-prototype`
- `vertical-clustering-investigation`
- `verification-repair-stage-ablation`
- `verification-reconciliation-slice2-decision`

The current advertised remote branches are `guh` and `master`; `master` was not
part of the cleanup. Retirement removed branch references only. The accepted
research commits, including `9867a0d0f19d22cc9f102f6c94cd2c2c58cd0fed`, remain
reachable from `guh`, and the research records and artifacts remain in the
repository. No research finding authorized a production geometry change; the
Slice 2 technical conclusion is unchanged.
