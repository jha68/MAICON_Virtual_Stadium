# WINGBOT UGV model

The reference stadium uses `wingbot_6wd_v1`. Synthetic protocol fixtures keep
their original model. The public participant interface and automatic M2–M6
mission flow are unchanged.

Source: [prestudy(2), original PDF](https://github.com/jha68/MAICON/blob/main/materials/prestudy%282%29_2026MAICON.pdf),
pages 3–4 (6WD and component layout), 14–16 (control API), and
[prestudy(1)](https://github.com/jha68/MAICON/blob/main/materials/prestudy%281%29_2026MAICON.pdf), M4 rules.

| Documented property | Simulation |
| --- | --- |
| 250 W × 230 L × 320 H mm | Same neutral envelope; six rubber wheels, three per side |
| 6WD, forward/reverse and yaw commands | Differential planar drive; left/right wheel animation follows actual displacement and turning |
| Linear ±0.6 m/s, angular ±3 rad/s | Same API limits; existing acceleration ramp and 0.5 s command watchdog |
| Pan ±50°, tilt ±15° | Same servo limits and signs; optics move with the physical gimbal |
| Laser above RGB camera | Separate calibrated lens origins; 52 mm estimated vertical separation |
| Left/right receiving sensors | White outward-tilted hemispherical domes with opaque backing |
| 5 s emission, 10 s start-to-start firing | Continuous ray, not projectiles; one ammunition charge per accepted firing |
| 2 s continuous reception | Per-receiver dwell; switching sides or losing line of sight resets continuity |
| 4 HP, 8 rounds, hit lock/invulnerability | Existing contest rules retained |

`core/robot_model.py` creates the procedural meshes used by PyBullet camera RGB
and the browser 3D view. Chassis, deck, turret housings and receiver backing are
opaque analytic proxies; only the exposed dome surface is a receiving area.
The shared lens transform controls both hit rays and the observer's red guide
line, which stops at the first obstacle. The guide is an operator aid, not a
beam painted into participant RGB. The 2D view uses the same receiver positions.
Double-click the 3D view to focus the selected UGV; double-click again to return
to the stadium. Drag to orbit and use the wheel to zoom.

Image-only M4 detection reads camp sleeves and their one/two/three black rings,
then requires a visible white dome at the model's expected scale. Smaller white
headlights are rejected. No opponent pose, HP, ammunition or simulator ID is
fed into that detector. Status remains unknown when the individual indicators
cannot be read. M6 remains the separately labelled mock requested earlier.
Overhead navigation pairs the visible white domes with nearby camp sleeves;
central HP lamps are excluded as identity evidence, and conflicting camp colours
cause abstention. These anonymous position estimates never authorize firing.

## Unmeasured parameters

`SIM-WINGBOT-PHOTO`: device offsets, 26 mm dome radius, dome tilt, 40 mm wheel
radius and 205 mm axle width are proportions inferred from the photo. Dome
acceptance is an exposed-hemisphere geometric approximation, not a measured
photodiode response. The zero-width ray, ideal optical alignment and occlusion
proxies do not model beam divergence, ambient interference or pulse electronics.

Acceleration (0.8 m/s², 6 rad/s²), the servo acceleration gain and tire slip are
not hardware-calibrated; this remains the shared planar simulator, not a rigid
body/dynamic friction model. Nominal mass is about 2.9 kg in the source, but the
kinematic solver does not claim a measured mass/inertia response. The policy's
cruise speed is separate from the documented API maximum; no artificial speed
increase is introduced by this visual update.

The camera's advertised 160° specification does not provide calibrated axes,
distortion or rectification. The existing explicit 640×480 rectified 90°
simulation intrinsics are retained until measured camera calibration is supplied.
These estimates are isolated from documented API values and are replaceable.
