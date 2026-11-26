# StillCurrent

StillCurrent audits a local Git snapshot for stale guidance, misplaced or potentially unused code and assets, and tracked files that violate an artifact policy. It produces a rating for the configured scope and an evidence trail for each finding.

## Run it

Requires Git and Python 3.9 or newer. Run the executable directly. The scan needs no package install, network access, or AI account.

```sh
./stillcurrent /path/to/checkout
./stillcurrent /path/to/checkout --rev origin/main --profile profiles/ancestor-book.json
./stillcurrent /path/to/checkout --rev origin/main --profile profiles/ancestor-book.json --format markdown
./stillcurrent /path/to/checkout --rev origin/main --profile profiles/ancestor-book.json --format json
```

The default revision is `HEAD`. Use any local commit, branch, or tag with `--rev`. The scanner reads tracked content from that revision and ignores working-tree edits. Scan your staged changes after committing them to a review branch. `--as-of YYYY-MM-DD` fixes the date used for retention checks and makes reports reproducible.

Findings exit with code 0 so the first release can run in advisory mode. Invalid input and failed scans exit with code 2.

## Configure the scope

Place `.stillcurrent.json` on the revision you want to scan or pass an external file with `--profile`. The [Ancestor Book profile](profiles/ancestor-book.json) is a worked example. Pick maintained entry points and declare what needs checking in each workflow before using the score as a baseline.

| Field | Check |
| --- | --- |
| `scope` | Display name for the audit scope. |
| `docs` | Markdown paths to check for common inline and reference-definition links to tracked local paths. Defaults to tracked root `README.md` and `AGENTS.md`. |
| `decisions` | Decision record paths. At the top of each record, add front matter with `status: current` or `status: superseded` and a plain relative `superseded_by: path.md`. A supersession chain must end at a current record. |
| `claims` | Known stale phrases and their witnesses. Supply `id`, `path`, `stale_contains`, `witness_path`, `witness_contains`, `title`, and `next_step`. A missing witness leaves the check unresolved. |
| `references` | Supply `id`, `path`, `search` (Git pathspec list), and `expectation` (`move`, `retained`, or `retire`). Search for the file path or supply a literal `token`, including a URL or filename when applicable. `retained` can require a `path_contains` witness in the retained file. A still-tracked retirement candidate with no matches is unresolved. |
| `artifact_rules` | Supply `id`, `patterns` (case-sensitive glob list matched against tracked paths), `title`, and `next_step`. For artifacts under a time-limited policy, set inclusive `retain_until` as `YYYY-MM-DD`. Python bytecode and Finder metadata checks are built in. |

Claim, reference, and artifact rules accept `impact` of `high`, `medium`, or `low`. Claims and references can set `critical: true` so an unresolved result withholds the rating.

## Read the rating

Knowledge contributes 40%, code and assets 35%, and artifacts 25%. Each area score is passes divided by evaluated checks. Coverage is evaluated checks divided by configured checks in that area. An area needs at least 80% coverage, and critical checks must be resolved, before the tool reports a weighted total. A default scan without code or asset checks will withhold the total.

The report shows checklist coverage. Generalizing beyond those checks requires a broader profile. Link checks cover local file paths. Anchors, external links, and claims about deployed environments require separate evidence. Literal references miss dynamically generated paths and consumers outside the snapshot. Confirm those consumers and retention requirements before removing anything.
