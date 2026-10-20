# Contributing

Use Python 3.11 and run `./run.ps1 test` and `./run.ps1 smoke` before proposing a
change. Keep audio processing causal, queues bounded and camera exposure time
distinct from delivery time. Add a regression test when a change affects those
contracts. Tests should use generated data, not microphones, private recordings
or model downloads.

Keep historical results unchanged. Put new measurements in a separate directory
with their build identity, configuration, raw observations and failure cases.
Label estimates and simulation explicitly. Do not turn missing observations into
zero latency or claim physical evidence from a synthetic fixture.

Retain upstream notices when changing vendored code and document the change.
Do not upload personal media or datasets without permission and a clear licence.
