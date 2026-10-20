# Architecture

## Voice

`relay_voice.rt.engine.Pipeline` accepts exactly 240 mono samples at 48 kHz and
returns the same number synchronously. A causal FIR reduces the rate, the selected
character transform processes one block, and a stateful FIR reconstructs 48 kHz.
The default operates internally at 24 kHz. It applies a development-selected noise
gate around the character transform. State belongs to one stream.

The callback records driver timestamps and compute time in a bounded telemetry
ring. An exception or missed deadline enters safe mute. Device reconnection
discards stale state. No queue is allowed to accumulate converted speech.

The optional MeanVC2 adapter uses larger packets and a fixed reservoir to reconcile
model output cadence. It can starve or miss its deadline; those are observed
limitations, not reasons to grow the reservoir indefinitely.

## Camera and state transport

The simulator publishes joint states, noisy simulated odometry and independent
camera messages over local ZeroMQ. Head images form a stereo pair. Wrist images
use a KB4 fisheye model and simulated ideal depth. Each frame carries a capture
epoch and a separate send epoch; a delayed image must keep its original capture
time.

Replay re-bases those epochs to the current host clock. Recorded send order
preserves late delivery; recorder disk time is not treated as camera exposure.
The included synthetic fixture exercises this transport contract, not rendering
or tracking accuracy.

## Fusion and display

The transform buffer interpolates observed robot state at exposure time. Stereo
or declared simulated depth is projected into a bounded voxel map. Ray evidence
supports, ages or suppresses the fixed Gaussian prior. Live surfaces, stale live
surfaces, verified/unverified old map, removed regions and unknown coverage remain
distinct states in the operator view.

The operating fusion/UI/kinematics modules do not import simulator truth or read
evaluation ground truth. Unit tests enforce that boundary. Evaluation truth is
recorded separately when a simulation experiment asks for it.

Capture-to-DOM covers accepted geometry reaching browser bookkeeping. It does not
measure photons on a monitor, time to understand a changed object, or command to
visible motion. A high browser redraw rate is also distinct from fresh geometry.
