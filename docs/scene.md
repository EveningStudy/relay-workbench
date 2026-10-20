# Scene and robot guide

## Procedural operator view

From the root after setup:

```powershell
.\run.ps1 scene
.\run.ps1 operator
```

Open [the local operator view](http://127.0.0.1:8090). The generated prior is an
unmeasured procedural desk, not the historical real scan. Robot meshes and its
URDF are generated from `scene_robot/configs/robot.yaml`. Gaussian attributes are
written in standard PLY form and displayed by Viser.

## Small camera/state replay

Run `./run.ps1 smoke` first to create the tiny fixture. With the operator running,
open a second PowerShell at the repository root:

```powershell
$env:PYTHONPATH = "$PWD/scene_robot"
.\.venv\Scripts\python.exe -m p2.io.replay_node outputs/synthetic_episode --speed 1 --output-log outputs/viewer_replay.json
```

This one-second generated pattern episode supplies four camera streams, joints
and odometry. Its images and depth are deliberately simple transport fixtures,
not physically rendered desk observations. It is useful for checking feed/status
updates. Run it again to replay. Port 5600 must have only one producer at a time.

## Optional full simulator

SAPIEN rendering requires a compatible graphics/Vulkan environment. This path is
outside the CPU-only smoke check. In the existing local environment:

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
selection and smooth presets are available in the panel. The optional simulator
installation and live GPU rendering were not revalidated for the public copy.

The original fixed scan, fitted home geometry, phone calibration, human teleop
episodes and phone/webcam/OBS recordings are excluded. Supplying a new real scan
also requires scale/pose alignment and an appropriate collision scene; copying a
PLY into the procedural example does not establish that alignment.
