# Verification

Checked on Windows x64 with Python 3.11.17, using this repository's setup and task
launchers. No personal input, neural checkpoint or GPU was used for these checks.

| Check | Outcome | Scope |
| --- | --- | --- |
| `setup.ps1 -Python <Python-3.11-executable>` | Passed | Fresh local venv, Internet package install, hashed CPU lock. |
| `python -m pip check` in the venv | Passed | Installed package requirements consistent. |
| `run.ps1 test` | 69 passed | Original lightweight suites and synthetic default replay. |
| `run.ps1 smoke` | Passed | 48,000 audio samples; 80 camera frames, 20 joint and 20 odometry messages. |
| `run.ps1 scene` | Passed | Generated robot and 11,998 procedural Gaussians. |
| `run.ps1 operator` | Passed with renderer diagnostic below | CPU map and procedural prior loaded. |
| Browser interaction | Passed | Chrome 1440x1000; canvas focus, right-arm selection, STOP response. |
| `python scripts/results.py --check` | Passed | Page matches retained numerical summaries; no experiment rerun. |
| Release audit | Passed | Text, paths, subtitle text, media metadata, size limits and private disallowed-term list. |
| Source preservation | Passed | 51,680 source files retain their SHA-256 digests and source Git HEAD is unchanged. |

## Browser check

The Browser plugin was unavailable, so the check used installed Chrome through
Playwright. The correct page title and meaningful scene/control content rendered.
There was no framework overlay. Right-arm selection changed the visible banner;
STOP remained responsive. The screenshot and orbit GIF are from this actual
procedural operator view.

![Procedural operator view](media/operator.png)

Pinned Viser/Three.js emits a nonfatal `computeBoundingSphere` diagnostic for an
instanced Gaussian quad with two-component positions. Inspection found zero
nonfinite values in that position buffer. The scene remains visible and interactive.
There are also upstream clock-deprecation and shader-precision warnings. These
are retained findings, not a clean-console claim.

## What this does not verify

No physical microphone/output run, listening study, new WER evaluation, neural
model installation, full GPU simulation or historical benchmark was rerun. The
small episode is a generated image/depth pattern fixture. It verifies decode,
state and transport only; publishing messages does not by itself verify receipt
by a viewer or validate geometry quality.

The original build's measurements remain historical evidence. Repackaging and
passing functional tests do not make them measurements of this renamed CPU setup.
