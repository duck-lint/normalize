# Slice 2 branch topology and consolidation plan

Audit basis: local and remote refs inspected on 2026-09-22 from
`verification-reconciliation-slice2-decision`, with no merge, rebase, deletion,
remote-ref update, or force-push performed.

## Repository topology

The remote is `origin` (`https://github.com/duck-lint/normalize`). Its advertised
HEAD and the local default-tracking branch are `origin/guh`; local `guh` is at
`a2ccdb1f06f3e97fbcc437fb969636305031355f`. `origin/master` is an older
ancestor, not the remote default. The remote `origin/slice2/geometry-probe-checkpoint`
ref is stale according to `git remote show origin` and is also an ancestor of
`origin/guh`.

All six published research tips form a linear descendant stack from `guh` and
are ancestors of the current candidate. Each has zero commits unique relative
to the current candidate; its listed tip commit is the incremental research
commit at that stage.

| Ref | Tip SHA | Remote/upstream | Relation to candidate | Unique work | Proposed action |
| --- | --- | --- | --- | --- | --- |
| `guh` / `origin/guh` | `a2ccdb1f06f3e97fbcc437fb969636305031355f` | tracked; default | ancestor, merge base | base Slice 2 history | destination; do not alter in this task |
| `geometry-forensics-identity-oracle` / origin | `6453d2890fce5799640d7219effdd090ea6aed2d` | tracked, up to date | ancestor; +1 from default | residual evidence and identity oracle | archive after integration approval |
| `diagnostic-investigation-sparse-vertical` / origin | `d2dbea8e8e1a51ad92b38bb2caddb7f209542e72` | tracked, up to date | ancestor; +2 | sparse/vertical diagnostics | archive after integration approval |
| `evidence-corrections-pixel-experiments` / origin | `699771d01c1a83c6f89c6a7eb2102e79a709b671` | tracked, up to date | ancestor; +3 | evidence corrections and errata | archive after integration approval |
| `pixel-evidence-prototype` / origin | `c0f7ea88493a07e6139e9c71d413a2eda130c17b` | tracked, up to date | ancestor; +4 | research pixel measurements | archive after integration approval |
| `vertical-clustering-investigation` / origin | `dfa6cd1ef2387364dded5ba86f92635d94875b4d` | tracked, up to date | ancestor; +5 | non-greedy comparison | archive after integration approval |
| `verification-repair-stage-ablation` / origin | `00fcabf7f01557fb81b3aafdf04711aff13d2e48` | tracked, up to date | parent of candidate; +6 | verification repair and stage ablation | retain until candidate is accepted; then archive |
| `verification-reconciliation-slice2-decision` | `00fcabf7f01557fb81b3aafdf04711aff13d2e48` | no upstream; current worktree | candidate; +6 before this task's commit | this reconciliation, tests, and records | proposed PR source |
| `origin/master` | `93c6ef1ead9fd30aaf94b210a79aa2c6a39a16ff` | remote only | ancestor of default; not destination | older default line | retain unless repository owner changes policy |
| `origin/slice2/geometry-probe-checkpoint` | `4998f8c9d2a40bf6e9b62d04ec916ca382ea693c` | remote stale ref | ancestor of default; +4 behind default | historical checkpoint | do not prune without owner approval |

There is one worktree, at the repository path, currently associated with the
candidate branch. At audit time the only uncommitted state was the intended
verification test edit; no other branch has a worktree-associated change.
The published refs themselves are clean immutable pointers.

## Safe consolidation sequence

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

The only approval-dependent actions are PR creation if repository policy
requires it, merging, and any local/remote branch deletion or stale-ref prune.
None of those actions was performed here.
