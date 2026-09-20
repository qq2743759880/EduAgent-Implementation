# G10 Rollback Drill

Status: playbook complete; live rehearsal is intentionally deferred to the end of the page-by-page clay rollout.

## Preconditions

1. Run only on `feature/opt-waves` or a disposable drill branch created from it.
2. Record `git status --short` and preserve every unrelated user change.
3. Confirm frontend `3322` and backend `9988` are healthy.
4. Resolve the exact commit and files before every revert. Never use `git reset --hard`, `git clean`, or force push.
5. Save all command output under `test-reports/g10-rollback/<timestamp>/`.

Common verification commands:

```powershell
$env:CHECK_DEMO_BACKEND = 'http://127.0.0.1:9988'
& 'edu-agent/.venv/Scripts/python.exe' 'edu-agent/scripts/eval/febe_contract_check.py' --quiet
node 'edu-agent/scripts/check-demo.mjs' --frontend-port 3322
node 'scripts/gates/dom-hook-inventory.mjs' --all --check --out 'test-reports/g10-rollback/current'
node 'scripts/gates/style-dep-gate.mjs' --all --out 'test-reports/g10-rollback/current'
```

`check-demo.mjs` supplies the current 3322/9988 runtime health path. The older `verify_pages_cdp.mjs` still hardcodes retired ports 3000/8000, so it is not an acceptable G5 command until separately migrated.

## Scenario A: Single-page revert

Purpose: prove one page can return to its previous visual commit without reverting another page or the L2 theme.

1. Locate the page commit and inspect its complete file set:

```powershell
$pageCommit = '<page-commit-sha>'
git show --stat --oneline $pageCommit
git diff "$pageCommit^" $pageCommit -- 'edu-frontend/public/<page>.html'
```

2. Confirm the commit follows the page-only rule. If it also changes `theme.css`, stop and use Scenario B.
3. Create a disposable drill branch and revert the page commit:

```powershell
git switch -c 'codex/g10-single-page-drill'
git revert --no-edit $pageCommit
```

4. Restart the frontend only when the reverted page is an entry route or the dev server retains stale output.
5. Run G1, `check-demo`, G3, and the new G6 single-page check:

```powershell
node 'scripts/gates/style-dep-gate.mjs' --page 'http://127.0.0.1:3322/<page>.html' --out 'test-reports/g10-rollback/single-page'
```

6. Pass criteria:
   - the target page matches its pre-rollout behavior;
   - unrelated page commits remain present;
   - G1 has zero blocking drift;
   - runtime health and console checks do not add failures;
   - G3 frozen hooks remain unchanged.

## Scenario B: `theme.css` revert

Purpose: prove the global L2 token layer can roll back as one unit and that all page references resolve to one matching version.

1. Inspect the candidate commit and confirm the blast radius:

```powershell
$themeCommit = '<theme-commit-sha>'
git show --stat --oneline $themeCommit
git show --name-only --format='' $themeCommit
```

2. Revert the theme commit on a disposable branch:

```powershell
git switch -c 'codex/g10-theme-drill'
git revert --no-edit $themeCommit
```

3. If page commits reference a version introduced by the reverted theme commit, revert the corresponding version-reference commit in the same drill. Do not hand-edit 25 pages during a rollback.
4. Run the common verification commands plus G8:

```powershell
node 'scripts/gates/asset-cache-gate.mjs' --all --out 'test-reports/g10-rollback/theme'
```

5. Pass criteria:
   - every page resolves `theme.css` without 404;
   - every page uses one identical non-empty `?v=` value;
   - zero non-loopback requests are introduced;
   - G1, runtime health, and G3 remain at or better than the recorded pre-drill baseline.

## Scenario C: Cache cleanup and cold restart

Purpose: eliminate a mixed state where stale HTML loads a new stylesheet, or new HTML loads an old stylesheet.

1. Stop the frontend with the repository script:

```powershell
& '.\stop-eduagent.cmd'
```

2. Resolve and validate the exact `.next` directory before deletion:

```powershell
$nextPath = (Resolve-Path -LiteralPath 'edu-frontend/.next').Path
$frontendPath = (Resolve-Path -LiteralPath 'edu-frontend').Path
if ([IO.Path]::GetFileName($nextPath) -ne '.next') { throw 'Refusing unexpected cache target.' }
if (-not $nextPath.StartsWith($frontendPath + [IO.Path]::DirectorySeparatorChar)) { throw 'Cache target escaped edu-frontend.' }
Remove-Item -LiteralPath $nextPath -Recurse -Force
```

If `.next` does not exist, record that fact and continue; do not broaden the deletion target.

3. Start services and wait for health:

```powershell
& '.\start-eduagent.cmd'
Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:3322/login-register.html?cache-drill=1'
Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:9988/health'
```

4. Run the common verification commands and G8 again.
5. Pass criteria:
   - cold-start responses are 200;
   - cache-busted HTML and `theme.css?v=<version>` resolve together;
   - no local assets return 404;
   - no new G1/G3/runtime failures appear.

## Rehearsal record

| Date | Scenario | Drill branch | Reverted commit(s) | G1 | Runtime/G5 proxy | G3 | G8 | Result | Evidence path |
|---|---|---|---|---|---|---|---|---|---|
| Pending rollout close | A | - | - | - | - | - | N/A | NOT RUN | - |
| Pending rollout close | B | - | - | - | - | - | - | NOT RUN | - |
| Pending rollout close | C | - | N/A | - | - | - | - | NOT RUN | - |

The rehearsal is complete only after at least one row has real commits, command output, and a PASS/FAIL decision. A written playbook alone does not make G10 green.
