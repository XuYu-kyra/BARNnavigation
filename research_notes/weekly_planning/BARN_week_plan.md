# BARN Week Plan

## What this week is really about

This week is not about "keep running world 0 until it works".
This week is about building a defensible baseline for later fault-injection work:

1. understand what BARN is and why it exists;
2. understand how the 300 static worlds were generated and ranked;
3. understand what the current ROS 2 baseline is actually running;
4. define a world-selection method that is better than arbitrarily picking world 0.

## Paper facts to extract from `Benchmarking Metric Ground Navigation`

Use these points in notes, slides, and dissertation justification:

- BARN was proposed because navigation systems are often evaluated in ad hoc ways, such as one or two hand-picked environments, which makes comparison weak and subjective.
- The dataset contains 300 static navigation environments for metric ground navigation.
- The environments are generated with a cellular automaton, then filtered so a valid path exists between start and goal.
- The paper uses a robot C-space derived from the robot footprint rather than raw obstacle geometry alone.
- The five key difficulty metrics are:
  - distance to closest obstacle
  - average visibility
  - dispersion
  - characteristic dimension
  - tortuosity
- The original paper benchmarks difficulty by running navigation systems repeatedly and ordering environments by measured traversal difficulty, not by visual intuition alone.
- The paper's benchmark logic directly supports the claim that you should not justify experiments by testing only one or two arbitrary worlds.

## Facts from the ROS 2 BARN repository

### Static worlds only for your current stage

- The current ROS 2 README says "No DynaBARN worlds."
- The `jackal_helper/worlds/BARN` folder contains `world_0.world` to `world_299.world`, plus matching `path_*.npy` files.
- `BARN_runner.launch.py` treats `world_idx < 300` as static BARN and `300-359` as DynaBARN, but the current repo README says not to use DynaBARN yet.

### The current ROS 2 baseline is not the same as the original paper baseline

The original paper used:

- global path from A*
- local navigation systems benchmarked with DWA and E-Band

The current ROS 2 repo uses Nav2 with:

- global planner: `nav2_navfn_planner::NavfnPlanner`
- `use_astar: false`, so this config is using NavFn's Dijkstra mode, not A*
- local controller: `nav2_mppi_controller::MPPIController`
- recovery/behavior plugins: `spin`, `backup`, `drive_on_heading`, `assisted_teleop`, `wait`

So your write-up should clearly separate:

- the original BARN benchmark definition from the 2020 paper; and
- the specific ROS 2 baseline implementation you are running in this repository.

### What a single ROS 2 run is actually doing

- README example launch runs `ros2 launch jackal_helper BARN_runner.launch.py world_idx:=0`
- `BARN_runner.launch.py` sets a static-world goal distance of 10 m
- `barn_runner.py` uses:
  - initial pose `[-2.25, 3, 1.57]`
  - goal offset `[0, 10]`
  - timeout `100` seconds
  - success condition: robot gets within `1` meter of the goal
- `barn_runner.py` reports one of:
  - succeeded
  - collided
  - timeout
- It also computes a navigation metric based on success and time relative to path length

This means a timeout on `world 0` currently proves only this:

- the present Nav2 baseline did not complete that run within the configured success/timeout rules

It does **not** yet prove:

- `world 0` is a bad world;
- the benchmark is faulty; or
- BARN is unsuitable.

## What you should produce today

### Task 1. Paper note

Write a one-page note with four mini-sections:

1. why BARN was proposed;
2. how the 300 worlds were generated;
3. what the difficulty metrics mean;
4. how benchmark performance is defined.

If you only finish one reading task today, finish this one.

### Task 2. Baseline characterization note

Record the current ROS 2 baseline as a table:

- simulator: Gazebo / ROS 2 Jazzy stack in this repo
- robot: Jackal
- planner: NavFn global planner
- controller: MPPI
- behaviors: spin / backup / drive_on_heading / assisted_teleop / wait
- goal rule: predefined start to goal
- success rule: within 1 m of goal
- failure rules: collision or 100 s timeout

This table is what your supervisor meant by "understand what algorithms are being used".

### Task 3. World-selection protocol

Define a world-selection method before more experiments:

1. exclude dynamic worlds;
2. work only with static `world_0` to `world_299`;
3. do not justify selection as "I happened to start with world 0";
4. use the paper's difficulty logic to choose representative worlds;
5. choose at least easy / medium / hard examples for diagnosis.

For this week, a sensible minimal target is:

- 1 easy world
- 1 medium world
- 1 hard world

If time allows, use 2 worlds per band.

## A practical decision rule for next runs

Do **not** spend the whole week trying to rescue `world 0` first.

Instead:

1. characterize the current baseline stack;
2. inspect several static worlds across difficulty;
3. see whether timeout is unique to world 0 or common across easier worlds too;
4. only then decide whether `world 0` indicates a config issue, a baseline weakness, or simply a difficult case.

That is a much stronger engineering process than repeatedly launching one world.

## Questions to stop asking

Avoid questions like:

- "Is this enough evidence?"
- "Can you tell me if my decision is okay?"
- "Should I just keep world 0?"

Those questions are weak because they outsource the judgment that your supervisor wants you to develop.

## Better questions for the next meeting

Ask questions that show analysis and a concrete decision point:

1. "The 2020 BARN paper defines the benchmark using 300 ranked static worlds, while this ROS 2 repo currently runs a Nav2 baseline with NavFn + MPPI rather than the paper's DWA/E-Band systems. I plan to document those as separate layers: benchmark definition vs implementation baseline. Is that framing appropriate for the dissertation?"

2. "Rather than selecting world 0 arbitrarily, I plan to sample representative static worlds across easy, medium, and hard difficulty bands before fault injection. My goal is to characterize baseline behavior across those bands first. Does that scope sound proportionate for the next stage?"

3. "If the baseline times out in one world but succeeds in easier representatives, I will treat that as evidence about environment sensitivity rather than as an immediate repo bug. Is that a reasonable interpretation strategy?"

These are much stronger than asking for permission or confidence.

## One repo issue to keep in mind

`test.sh` says it runs 50 equally spaced worlds `[0, 6, 12, ..., 294]`, but the loop currently starts at `i=7`, so it actually starts from `world 42`.

Do not cite that script blindly in your notes without checking it.
