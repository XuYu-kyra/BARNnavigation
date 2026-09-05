# BARN ROS2 Structure Analysis

## Purpose

This note answers the four questions you need for the feasibility-stage "how it works" analysis:

1. what `BARN_runner.launch.py` does;
2. which Nav2 bringup file is actually used;
3. which planner / controller / behavior / goal checker / progress checker are active;
4. what the full flow is from world load to benchmark result.

## 1. Top-level entry point

The normal single-run entry point is:

- `ros2 launch jackal_helper BARN_runner.launch.py world_idx:=0`

The batch benchmark entry point is:

- `test.sh`, which repeatedly launches `BARN_runner.launch.py` for multiple worlds

So for structure analysis, the first file to understand is:

- `jackal_helper/launch/BARN_runner.launch.py`

## 2. What `BARN_runner.launch.py` does

`BARN_runner.launch.py` is the **orchestrator** of the whole benchmark run. It does not itself plan paths or compute control commands. Its job is to set up simulation, spawn the robot, launch Nav2, send the navigation goal, and start the benchmark monitor.

### 2.1 Launch arguments

It declares the key run arguments:

- `rviz`
- `gui`
- `world_idx`
- `setup_path`
- `out_file`
- `timeout`
- `throttle_duration`

For static BARN worlds:

- `world_idx < 300`
- the selected world is `BARN/world_<idx>.world`
- the goal distance is fixed to `10` meters

### 2.2 Gazebo and bridge setup

The function `launch_ros_gazebo(...)`:

- loads the chosen Gazebo world;
- launches `ros_gz_sim`;
- creates a `ros_gz_bridge` node called `clock_bridge`.

That bridge exposes:

- `/clock`
- `/world/default/control`
- `/world/default/set_pose`
- `/robot/touched`
- `/model/robot/pose`

These are important because later:

- `barn_runner.py` uses `/world/default/set_pose` to reset the robot;
- `barn_runner.py` uses `/robot/touched` to detect collisions;
- `barn_runner.py` uses `/model/robot/pose` to read robot pose.

### 2.3 Robot spawn

The function `spawn_jackal(...)`:

- includes Clearpath's `robot_spawn.launch.py`;
- uses `setup_path` to load the robot configuration;
- spawns the robot at `x=2.0, y=2.0, z=0.3`;
- remaps `/sensors/lidar2d_0/scan` to `/front/scan`.

This remap matters because Nav2 is later configured to consume the front scan topic.

### 2.4 Nav2 launch and goal publication

The function `launch_navigation_stack(...)`:

- includes `jackal_helper/launch/nav2_bringup.launch.py`;
- passes:
  - `use_sim_time=true`
  - `setup_path=<...>/config`
  - `scan_topic=/front/scan`
  - `nav2_params_file=nav2.yaml`
  - `log_level=WARN`

It also:

- registers an exit handler on `bt_navigator`;
- constructs a `NavigateToPose` goal in the `odom` frame;
- sends that goal to `/navigate_to_pose` through `ros2 action send_goal`.

### 2.5 Benchmark monitor startup order

`generate_launch_description()` uses timers:

- start `barn_runner.py` after `10` seconds;
- start the Nav2 stack after `15` seconds;
- after Nav2 is launched, wait another `10` seconds before sending the goal.

So the rough order is:

1. launch Gazebo;
2. spawn Jackal;
3. start benchmark monitor;
4. launch Nav2;
5. send navigation goal;
6. wait for movement, monitor collision/time/success, and score the run.

## 3. Which Nav2 bringup file is used

The Nav2 bringup file actually used by BARN ROS2 is:

- `jackal_helper/launch/nav2_bringup.launch.py`

This is **not** the stock `nav2_bringup` launch file directly. It is a local wrapper adapted from Nav2's Jazzy bringup.

Its job is to:

- load the parameter file;
- rewrite scan-topic parameters;
- remap odometry and TF topics;
- launch the Nav2 lifecycle nodes.

## 4. What `nav2_bringup.launch.py` does

### 4.1 Parameter loading

`jackal_nav2_setup(...)`:

- reads `robot.yaml`;
- builds a `RewrittenYaml`;
- rewrites every parameter named `topic` to the selected scan topic.

Because `BARN_runner.launch.py` passes `scan_topic=/front/scan`, this means the costmaps end up reading the front LiDAR topic rather than the original raw sensor topic string inside `nav2.yaml`.

### 4.2 Topic remapping

The launch file remaps:

- `/tf -> tf`
- `/tf_static -> tf_static`
- `/odom -> /platform/odom`

So Nav2 consumes robot odometry through the platform odom pipeline rather than a generic `/odom` source.

### 4.3 Lifecycle nodes launched

The bringup starts these Nav2 nodes:

- `controller_server`
- `smoother_server`
- `planner_server`
- `behavior_server`
- `velocity_smoother`
- `bt_navigator`
- `lifecycle_manager_navigation`

This is the active navigation stack in this repo.

## 5. What algorithms are active in `nav2.yaml`

The parameter file actually used is:

- `jackal_helper/config/nav2.yaml`

### 5.1 BT navigator

- navigator plugins:
  - `NavigateToPoseNavigator`
  - `NavigateThroughPosesNavigator`
- global frame: `odom`
- robot base frame: `base_link`
- odom topic: `platform/odom/filtered`

So this stack is running in the `odom` frame, not a `map` frame from AMCL.

### 5.2 Controller side

The controller stack uses:

- `controller_plugins: ["FollowPath"]`
- `FollowPath -> nav2_mppi_controller::MPPIController`

So the active local controller is:

- **MPPI**

This is important because it is different from the original 2020 BARN paper baselines such as DWA or E-Band.

### 5.3 Progress checker

The configured progress checker is:

- `nav2_controller::SimpleProgressChecker`

with:

- `required_movement_radius: 0.5`
- `movement_time_allowance: 10.0`

Meaning the controller expects measurable motion progress within that radius/time window.

### 5.4 Goal checker

The configured goal checker is:

- `nav2_controller::SimpleGoalChecker`

with:

- `xy_goal_tolerance: 0.25`
- `yaw_goal_tolerance: 0.25`
- `stateful: true`

### 5.5 Planner

The global planner is:

- `planner_plugins: ["GridBased"]`
- `GridBased -> nav2_navfn_planner::NavfnPlanner`
- `use_astar: false`

So this baseline is using:

- **NavFn in Dijkstra mode**, not A*

### 5.6 Smoother

The path smoother is:

- `nav2_smoother::SimpleSmoother`

### 5.7 Recovery / behavior

The behavior server enables:

- `spin`
- `backup`
- `drive_on_heading`
- `assisted_teleop`
- `wait`

These are the active recovery/behavior modules in this baseline.

### 5.8 Costmaps

#### Local costmap

The local costmap:

- uses `global_frame: odom`
- uses `robot_base_frame: base_link`
- is a rolling window
- uses:
  - `VoxelLayer`
  - `InflationLayer`

#### Global costmap

The global costmap:

- also uses `global_frame: odom`
- has no static layer plugin
- uses:
  - `ObstacleLayer`
  - `InflationLayer`

## 6. Important architectural observation: this is not a classical map-based Nav2 pipeline

The standard textbook Nav2 picture is often:

- LiDAR -> localization -> map -> global costmap -> planner -> controller

But this BARN ROS2 baseline is different.

What is **not** launched here:

- no `amcl`
- no `map_server`
- no `slam_toolbox`
- no explicit static-map layer

What **is** launched:

- odometry/TF-based navigation in the `odom` frame
- obstacle-based local and global costmaps
- NavFn planner + MPPI controller + behavior server

So the more accurate flow for this repo is:

- Gazebo world -> LiDAR + odom + TF -> obstacle costmaps in `odom` frame -> planner -> controller -> behavior recovery if needed -> benchmark monitor and score

That is a stronger and more correct description than saying "localization/map" if those nodes are not actually present.

## 7. Where odometry and sensing come from

### LiDAR

`robot.yaml` enables the robot sensors, including 2D LiDAR.

`lidar2d_0.yaml` bridges:

- Gazebo topic `/sensors/lidar2d_0/scan`
- to ROS topic `lidar2d_0/scan`

Then `BARN_runner.launch.py` remaps:

- `/sensors/lidar2d_0/scan -> /front/scan`

And `nav2_bringup.launch.py` rewrites `topic` parameters so Nav2 costmaps subscribe to `/front/scan`.

### Odometry

`platform/config/localization.yaml` defines an EKF node:

- `world_frame: odom`
- `base_link_frame: base_link`
- `odom0: platform/odom`
- `imu0: sensors/imu_0/data`

And `nav2.yaml` uses:

- `odom_topic: platform/odom/filtered`

So the intended odometry source for navigation is filtered platform odometry, likely produced by the Clearpath localization stack.

## 8. What `barn_runner.py` actually does

`barn_runner.py` is **not** the navigation algorithm.

It is the **benchmark runner / monitor / scorer**.

Its responsibilities are:

- declare benchmark parameters (`world_idx`, `out_file`, `timeout`);
- compute initial pose and goal pose;
- reset the robot to the initial pose through Gazebo services;
- wait until the robot starts moving;
- monitor:
  - current pose
  - elapsed time
  - collision status
- decide the run result:
  - `succeeded`
  - `collided`
  - `timeout`
- compute the navigation metric from the reference path length and actual time;
- append the result to the output file.

For static BARN worlds:

- initial pose: `[-2.25, 3, 1.57]`
- goal offset: `[0, 10]`
- success check: within `1` meter of goal
- timeout: `100` seconds by default

So:

- Nav2 decides how to move;
- `barn_runner.py` decides how to score the episode.

## 9. End-to-end run flow

The full flow is:

1. `BARN_runner.launch.py` selects the world from `world_idx`.
2. Gazebo loads `world_<idx>.world`.
3. `ros_gz_bridge` exposes clock, pose, collision, and world-control services to ROS 2.
4. Clearpath robot spawn launches Jackal and its platform/sensor stack.
5. LiDAR data becomes available and is routed to `/front/scan`.
6. Platform odometry and filtered odometry become available.
7. `nav2_bringup.launch.py` launches Nav2 lifecycle nodes with `nav2.yaml`.
8. `bt_navigator` receives a `NavigateToPose` goal in the `odom` frame.
9. `planner_server` computes a global path using NavFn.
10. `smoother_server` can smooth the path.
11. `controller_server` uses MPPI to generate velocity commands.
12. `velocity_smoother` smooths command velocity before output.
13. `behavior_server` provides recovery/behavior actions if the navigator requests them.
14. `barn_runner.py` watches pose, time, and collision.
15. When the robot succeeds, collides, or times out, `barn_runner.py` computes the benchmark metric and writes the result.

## 10. One-sentence summary for meetings

You can describe the current BARN ROS2 baseline like this:

"This repo uses `BARN_runner.launch.py` as the experiment orchestrator, launches a custom `nav2_bringup.launch.py`, runs a mapless Nav2 baseline in the `odom` frame with NavFn global planning, MPPI path following, standard Nav2 behavior plugins, and then uses `barn_runner.py` to monitor collision/time/success and compute the benchmark score."
