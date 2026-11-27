---
name: stillcurrent-cleanup
description: Resolve selected StillCurrent audit findings in a Git checkout and verify the cleanup with before-and-after evidence. Use when asked to act on a StillCurrent finding or validate a cleanup. A scan by itself calls for the CLI.
---

Work from the finding ID and the commit it came from. Find the StillCurrent executable in the tool checkout or on PATH. Read its README for CLI usage. Follow the target repository’s instructions for editing, committing, and verifying changes.

1. Reproduce the finding with the current CLI. Save a JSON audit from the baseline commit. Reuse the same explicit profile and `--as-of` date for the candidate. Store reports outside the target repo unless the user requests otherwise.
2. Read the finding’s cited files and trace what still depends on them. Look for callers in routes, builds, fixtures, external URLs, and supported legacy data as applicable. Resolve contradictory guidance against the maintained source for the relevant environment. When a dependency or retention requirement is unclear, record the missing evidence and leave the item open.
3. Make the smallest change that addresses the finding. Fix links and supersession pointers together. Move a live asset with its callers and packaging. Remove a candidate only after checking relevant consumers and retention. Preserve supported compatibility behavior.
4. Verify the candidate commit using `--compare baseline.json --finding FINDING_ID`. Use a check ID to require the full check to pass, or an individual ID from the JSON `findings` list to verify one issue under the check. Review `new_findings` and `regressions` before treating the cleanup as verified. Another issue under an already-failing check blocks verification even if the score stays the same. A change in scan settings calls for fresh baseline and candidate reports.
5. Verify affected behavior through the target repo’s normal checks. For an asset move, exercise a consumer against the packaged output. For a deletion, exercise the path that would fail if the item still had a consumer. For guidance, start from a normal entry point and check that the cited answer resolves. Report the finding ID, before and after commits, focused verification, and any remaining uncertainty.

A comparison verifies scanner findings only. Keep workflow evidence with the report and follow the user’s scope for commits, pushes, and merges.
