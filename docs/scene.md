# Scene and robot guide

## Kitchen operator view

From the root after setup:

```powershell
.\run.ps1 scene
.\run.ps1 operator
```

Open [the local operator view](http://127.0.0.1:8090). The preparation command
restores the packed, aligned kitchen scan and generates robot meshes/URDF from
`scene_robot/configs/robot.yaml`. All 216,953 Gaussians retain the exact 14 float32
properties consumed by this renderer. Packing omits unused normal and higher-order
SH fields without downsampling. See `scene_robot/assets/kitchen/manifest.json`.
The real reconstruction's holes and clutter remain visible.

The Gaussian prior is fixed. Physics and simulated RGB use fitted island/box/mug
primitives, a scan-derived tabletop texture and procedural floor/chair. They do
not render the full scan into every camera. Head cameras are pinholes; wrist
cameras use 180-degree fisheye projection. Wrist depth and odometry are simulated.

## Recorded robot-camera replay

With the operator running, use a second shell at the repository root:

```powershell
.\run.ps1 cameras --loops 3
```

The bundled 6.47 MB archive contains a 12-second historical simulator excerpt:
72 sampled RGB images per stream (6 fps), four robot streams plus an external
view used for media, and 20 Hz sampled joints/odometry. The publisher sends only
the four robot streams. Original capture/send ordering is retained and timestamps
are rebased for playback; the images are metadata-free JPEG re-encodes. This is
presentation replay, with no new timing or benchmark result.

No wrist depth, evaluation truth or full raw episode is bundled. Stereo may be
recomputed by the viewer, but this excerpt cannot reproduce the historical fusion
metrics. Run only one camera publisher on port 5600 at a time.

For a generated transport fixture, `run.ps1 smoke` still creates 80 simple
camera/depth frames and 20 joint/odometry messages. It is a functional check.

## Phone video and camera position in the scene

The phone GIF/comparison MP4 places approved source seconds 6-18 beside the kitchen
operator scene. The original checkerboard detector and PnP estimator derive the
phone's position/orientation from image corners, using measured board placement
and historical video-fitted intrinsics. These numerical calibration parameters
are bundled without calibration photos. The camera axes/frustum move only for
valid poses. Failed detections hide the current frustum; the trail keeps valid
history and does not connect across failures. There is no interpolation.

31/72 sampled frames have a pose; 41 do not. Reprojection residuals describe the
board fit, not independent world-space accuracy. This is an offline RGB pose
diagnostic, with no physical robot, depth fusion or hardware-latency measurement.

With the operator open, stop other camera publishers and run:

```powershell
.\run.ps1 phone --loops 3
```

Expand `real_phone` and `Real phone pose diagnostic` to see the recorded image,
board-pose status and scan-projection diagnostic. The scene's phone frustum is
hidden whenever no valid current pose is available. The full phone source and calibration photos are excluded. The
inspected USB test directory contains recovery logs but no saved RGB footage;
there is consequently no physical USB camera demonstration here.

## Optional full simulator

SAPIEN rendering requires a compatible graphics/Vulkan environment. It is outside
the CPU smoke check and was not revalidated for this media refresh.

```powershell
.\.venv\Scripts\python.exe -m pip install sapien==3.0.3
.\run.ps1 scene
# Shell A
.\run.ps1 operator
# Shell B
.\run.ps1 simulator --cameras configs/cameras.yaml --scenario configs/scenarios/empty.yaml --seconds 60
```

Click the canvas for keyboard focus. WASD moves the base; Q/E turns; arrows move
the head; R/F changes lift; T/G changes hip. Space/STOP cancels motion. Arm
selection and smooth presets are available in the panel. There is no physical robot.

## Rebuild the demonstrations

Stop other operator/simulator processes first:

```powershell
.\run.ps1 scene
.\.venv\Scripts\python.exe scripts/make_camera_media.py
.\.venv\Scripts\python.exe scripts/make_scene_media.py
```

Open `http://127.0.0.1:8090` within three minutes and keep the browser connected.
Viser's client renderer captures 144 frames for the 24-second, 6 fps scene GIF.
It updates recorded joint poses and camera lens outlines while orbiting the scan.
It does not run physics or receive live camera feeds during this offline capture.
The camera GIFs decode the bundled historical RGB, preserving fisheye aspect ratio.

To rebuild the synchronized phone demo from the bundled silent input:

```powershell
.\run.ps1 phone --prepare
.\.venv\Scripts\python.exe scripts/make_phone_pose_media.py
```

Stop the operator first, then open the render page as above. The script captures
72 Viser frames and pairs each with the corresponding undistorted phone frame.
`make_phone_media.py <owner-provided-source>` restores only the approved silent
input interval. The full source is intentionally absent. Kitchen/phone assets and their
derivatives have public display permission only, with no reuse licence; see
[licensing](licensing.md).
