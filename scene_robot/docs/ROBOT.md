# Relay robot

Provisional embodiment based on the brief architecture; no Relay reference CAD supplied.

Editable source: `configs/robot.yaml` and `p2/robot/gen_robot.py`. Regenerate with `python -m p2.robot.gen_robot`.

[proposal] Mesh volume times assumed homogeneous density from config supplies link masses and trimesh inertias. These are design assumptions, not hardware measurements. Collision uses bounding boxes. Self collision is disabled to avoid coincident virtual shoulder joints colliding; environment collision remains enabled. Gripper second fingers use URDF mimic joints.

Raw SAPIEN joint drives implement PD position control for upper body and velocity control for the holonomic virtual base. This replaces ManiSkill's wrapper after the M1 readback failure.

All dimensions, joint limits, efforts, velocities and masses in the following tables are [proposal] design values, generated from the config and procedural source.

| Joint | Type | Limits | Axis | Origin xyz | Origin rpy | Effort | Velocity |
|---|---|---|---|---|---|---|---|
| base_x | prismatic | (-3, 3) | (1, 0, 0) | (0, 0, 0) | [0, 0, 0] | 1500 | 0.5 |
| base_y | prismatic | (-3, 3) | (0, 1, 0) | (0, 0, 0) | [0, 0, 0] | 1500 | 0.5 |
| base_yaw | revolute | (-12.56, 12.56) | (0, 0, 1) | (0, 0, 0) | [0, 0, 0] | 1500 | 1.5 |
| column_mount | fixed | (-2.6, 2.6) | (0, 0, 1) | (0, 0, 0.18) | [0, 0, 0] | 80 | 1.5 |
| lift | prismatic | (0, 0.45) | (0, 0, 1) | (0, 0, 0.54) | [0, 0, 0] | 1500 | 0.15 |
| hip_pitch | revolute | (-0.2617993877991494, 0.7853981633974483) | (0, 1, 0) | (0, 0, 0) | [0, 0, 0] | 600 | 0.5 |
| head_pan | revolute | (-1.8, 1.8) | (0, 0, 1) | (0, 0, 0.38) | [0, 0, 0] | 80 | 1.5 |
| head_tilt | revolute | (-0.7, 1.1) | (0, 1, 0) | (0, 0, 0) | [0, 0, 0] | 80 | 1.5 |
| head_cam_left_mount | fixed | (-2.6, 2.6) | (0, 0, 1) | (0.12, 0.03, 0) | [np.float64(-1.5707963267948966), np.float64(0.0), np.float64(-1.5707963267948966)] | 80 | 1.5 |
| left_shoulder_pitch | revolute | (-2.6, 2.6) | (0, 1, 0) | (0, 0.2, 0.22) | [0, 0, 0] | 80 | 1.5 |
| left_shoulder_roll | revolute | (-2.6, 2.6) | (1, 0, 0) | (0, 0, 0) | [0, 0, 0] | 80 | 1.5 |
| left_shoulder_yaw | revolute | (-2.6, 2.6) | (0, 0, 1) | (0, 0, 0) | [0, 0, 0] | 80 | 1.5 |
| left_elbow | revolute | (-2.4, 0.0) | (0, 1, 0) | (0, 0, -0.29) | [0, 0, 0] | 80 | 1.5 |
| left_wrist_yaw | revolute | (-2.6, 2.6) | (0, 0, 1) | (0, 0, -0.25) | [0, 0, 0] | 80 | 1.5 |
| left_wrist_pitch | revolute | (-2.6, 2.6) | (0, 1, 0) | (0, 0, 0) | [0, 0, 0] | 80 | 1.5 |
| left_wrist_roll | revolute | (-2.6, 2.6) | (1, 0, 0) | (0, 0, 0) | [0, 0, 0] | 80 | 1.5 |
| wrist_cam_l_mount | fixed | (-2.6, 2.6) | (0, 0, 1) | (-0.02, 0.1, -0.15) | [np.float64(2.41238898038469), np.float64(2.220446049250313e-16), np.float64(-1.5707963267948968)] | 80 | 1.5 |
| left_palm_mount | fixed | (-2.6, 2.6) | (0, 0, 1) | (0, 0, -0.09) | [0, 0, 0] | 80 | 1.5 |
| left_finger_0_joint | prismatic | (0, 0.025) | (0, 1, 0) | (0, 0.025, 0) | [0, 0, 0] | 20 | 0.1 |
| left_finger_1_joint | prismatic | (0, 0.025) | (0, -1, 0) | (0, -0.025, 0) | [0, 0, 0] | 20 | 0.1 |
| head_cam_right_mount | fixed | (-2.6, 2.6) | (0, 0, 1) | (0.12, -0.03, 0) | [np.float64(-1.5707963267948966), np.float64(0.0), np.float64(-1.5707963267948966)] | 80 | 1.5 |
| right_shoulder_pitch | revolute | (-2.6, 2.6) | (0, 1, 0) | (0, -0.2, 0.22) | [0, 0, 0] | 80 | 1.5 |
| right_shoulder_roll | revolute | (-2.6, 2.6) | (1, 0, 0) | (0, 0, 0) | [0, 0, 0] | 80 | 1.5 |
| right_shoulder_yaw | revolute | (-2.6, 2.6) | (0, 0, 1) | (0, 0, 0) | [0, 0, 0] | 80 | 1.5 |
| right_elbow | revolute | (-2.4, 0.0) | (0, 1, 0) | (0, 0, -0.29) | [0, 0, 0] | 80 | 1.5 |
| right_wrist_yaw | revolute | (-2.6, 2.6) | (0, 0, 1) | (0, 0, -0.25) | [0, 0, 0] | 80 | 1.5 |
| right_wrist_pitch | revolute | (-2.6, 2.6) | (0, 1, 0) | (0, 0, 0) | [0, 0, 0] | 80 | 1.5 |
| right_wrist_roll | revolute | (-2.6, 2.6) | (1, 0, 0) | (0, 0, 0) | [0, 0, 0] | 80 | 1.5 |
| wrist_cam_r_mount | fixed | (-2.6, 2.6) | (0, 0, 1) | (-0.02, -0.1, -0.15) | [np.float64(2.41238898038469), np.float64(2.220446049250313e-16), np.float64(-1.5707963267948968)] | 80 | 1.5 |
| right_palm_mount | fixed | (-2.6, 2.6) | (0, 0, 1) | (0, 0, -0.09) | [0, 0, 0] | 80 | 1.5 |
| right_finger_0_joint | prismatic | (0, 0.025) | (0, 1, 0) | (0, 0.025, 0) | [0, 0, 0] | 20 | 0.1 |
| right_finger_1_joint | prismatic | (0, 0.025) | (0, -1, 0) | (0, -0.025, 0) | [0, 0, 0] | 20 | 0.1 |

## Embodiment figures

High-resolution source renders with red joint axes, blue stereo frusta and orange/pink 180-degree wrist hemispheres. All displayed dimensions are [proposal] values from the editable config; no hardware measurement is claimed.

![Front](evidence/relay_front_highres.png)
![Side](evidence/relay_side_highres.png)
![Top](evidence/relay_top_highres.png)
![Reach over desk](evidence/relay_reach_highres.png)
![Dimensions](evidence/relay_dimensions.svg)

Regenerate figures: `python -m p2.eval.robot_figures`. Camera/pose settings and design dimensions are logged in `docs/evidence/m19_robot.json`.

| Link | Mass kg | Size m | COM m |
|---|---|---|---|
| world | 0.01000 | None | (0, 0, 0) |
| base_slide_x | 0.01000 | None | (0, 0, 0) |
| base_slide_y | 0.01000 | None | (0, 0, 0) |
| base | 8.19527 | [0.5, 0.45, 0.16] | (0, 0, 0.1) |
| column_fixed | 2.43000 | [0.1, 0.1, 0.54] | (0, 0, 0.27) |
| lift_link | 1.56937 | [0.075, 0.075, 0.62] | (0, 0, -0.3) |
| torso | 7.12800 | [0.2, 0.36, 0.22] | (0, 0, 0.12) |
| head_pan_link | 0.37485 | [0.07, 0.07, 0.17] | (0, 0, -0.08) |
| head | 0.88145 | [0.16, 0.22, 0.11] | (0.035, 0, 0) |
| head_cam_left | 0.01000 | None | (0, 0, 0) |
| left_shoulder_pitch_link | 0.13980 | [0.085, 0.085, 0.085] | (0, 0, 0) |
| left_shoulder_roll_link | 0.13980 | [0.085, 0.085, 0.085] | (0, 0, 0) |
| left_shoulder_yaw_link | 0.53474 | [0.09, 0.09, 0.29] | (0, 0, -0.145) |
| left_elbow_link | 0.32013 | [0.075, 0.075, 0.25] | (0, 0, -0.125) |
| left_wrist_yaw_link | 0.13980 | [0.085, 0.085, 0.085] | (0, 0, 0) |
| left_wrist_pitch_link | 0.13980 | [0.085, 0.085, 0.085] | (0, 0, 0) |
| left_wrist_roll_link | 0.10199 | [0.07, 0.08, 0.08] | (0, 0, -0.04) |
| wrist_cam_l | 0.01000 | None | (0, 0, 0) |
| left_palm | 0.08505 | [0.06, 0.09, 0.035] | (0, 0, 0) |
| left_finger_0 | 0.01418 | [0.025, 0.018, 0.07] | (0, 0, -0.035) |
| left_finger_1 | 0.01418 | [0.025, 0.018, 0.07] | (0, 0, -0.035) |
| head_cam_right | 0.01000 | None | (0, 0, 0) |
| right_shoulder_pitch_link | 0.13980 | [0.085, 0.085, 0.085] | (0, 0, 0) |
| right_shoulder_roll_link | 0.13980 | [0.085, 0.085, 0.085] | (0, 0, 0) |
| right_shoulder_yaw_link | 0.53474 | [0.09, 0.09, 0.29] | (0, 0, -0.145) |
| right_elbow_link | 0.32013 | [0.075, 0.075, 0.25] | (0, 0, -0.125) |
| right_wrist_yaw_link | 0.13980 | [0.085, 0.085, 0.085] | (0, 0, 0) |
| right_wrist_pitch_link | 0.13980 | [0.085, 0.085, 0.085] | (0, 0, 0) |
| right_wrist_roll_link | 0.10199 | [0.07, 0.08, 0.08] | (0, 0, -0.04) |
| wrist_cam_r | 0.01000 | None | (0, 0, 0) |
| right_palm | 0.08505 | [0.06, 0.09, 0.035] | (0, 0, 0) |
| right_finger_0 | 0.01418 | [0.025, 0.018, 0.07] | (0, 0, -0.035) |
| right_finger_1 | 0.01418 | [0.025, 0.018, 0.07] | (0, 0, -0.035) |