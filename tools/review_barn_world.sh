#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  review_barn_world.sh --world WORLD_IDX [--preset tuned|original] [--setup-path PATH]
                       [--timeout SECONDS] [--gui true|false] [--rviz true|false]
                       [--log-level LEVEL] [--review-root DIR] [--throttle SECONDS]

Examples:
  review_barn_world.sh --world 173 --preset tuned
  review_barn_world.sh --world 94 --preset original --gui true --rviz true
EOF
}

WORLD=""
PRESET="tuned"
SETUP_PATH=""
TIMEOUT="300"
GUI="true"
RVIZ="true"
LOG_LEVEL="INFO"
THROTTLE="2"
REVIEW_ROOT="$HOME/dissertation/barn_ros2/manual_visual_review"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --world)
      WORLD="$2"; shift 2 ;;
    --preset)
      PRESET="$2"; shift 2 ;;
    --setup-path)
      SETUP_PATH="$2"; shift 2 ;;
    --timeout)
      TIMEOUT="$2"; shift 2 ;;
    --gui)
      GUI="$2"; shift 2 ;;
    --rviz)
      RVIZ="$2"; shift 2 ;;
    --log-level)
      LOG_LEVEL="$2"; shift 2 ;;
    --review-root)
      REVIEW_ROOT="$2"; shift 2 ;;
    --throttle)
      THROTTLE="$2"; shift 2 ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1 ;;
  esac
done

if [[ -z "$WORLD" ]]; then
  echo "Error: --world is required" >&2
  usage
  exit 1
fi

if [[ -z "$SETUP_PATH" ]]; then
  case "$PRESET" in
    tuned)
      CANDIDATE1="$HOME/dissertation/barn_ros2/experiment_setups/tuned_clean"
      CANDIDATE2="$HOME/dissertation/barn_ros2/src/The-Barn-Challenge-Ros2/experiment_setups/tuned_clean"
      ;;
    original)
      CANDIDATE1="$HOME/dissertation/barn_ros2/experiment_setups/original_clean"
      CANDIDATE2="$HOME/dissertation/barn_ros2/src/The-Barn-Challenge-Ros2/experiment_setups/original_clean"
      ;;
    *)
      echo "Error: unsupported preset '$PRESET'. Use tuned/original or pass --setup-path." >&2
      exit 1 ;;
  esac

  if [[ -f "$CANDIDATE1/robot.yaml" && -f "$CANDIDATE1/nav2.yaml" ]]; then
    SETUP_PATH="$CANDIDATE1"
  elif [[ -f "$CANDIDATE2/robot.yaml" && -f "$CANDIDATE2/nav2.yaml" ]]; then
    SETUP_PATH="$CANDIDATE2"
  else
    echo "Error: could not auto-detect a valid setup_path for preset '$PRESET'." >&2
    echo "Tried:" >&2
    echo "  $CANDIDATE1" >&2
    echo "  $CANDIDATE2" >&2
    echo "Pass --setup-path explicitly." >&2
    exit 1
  fi
fi

if [[ ! -f "$SETUP_PATH/robot.yaml" ]]; then
  echo "Error: missing $SETUP_PATH/robot.yaml" >&2
  exit 1
fi

if [[ ! -f "$SETUP_PATH/nav2.yaml" ]]; then
  echo "Error: missing $SETUP_PATH/nav2.yaml" >&2
  exit 1
fi

STAMP=$(date +%F_%H-%M-%S)
LOG_DIR="$REVIEW_ROOT/logs"
SHOT_DIR="$REVIEW_ROOT/screenshots"
NOTE_DIR="$REVIEW_ROOT/notes"
mkdir -p "$LOG_DIR" "$SHOT_DIR" "$NOTE_DIR"

LOG_PATH="$LOG_DIR/world_${WORLD}_${PRESET}_${STAMP}.log"
NOTE_PATH="$NOTE_DIR/world_${WORLD}_${PRESET}_${STAMP}.md"

cat > "$NOTE_PATH" <<EOF
# World $WORLD Review

- Preset: $PRESET
- Setup path: $SETUP_PATH
- Timestamp: $STAMP
- Expected checks:
  - final status: succeeded / timeout / collided
  - rough layout: open / narrow / cluttered / many turns
  - observed behaviour: smooth / oscillating / recovery / stuck
  - screenshot path:
  - notes:
EOF

cat <<EOF
Review starting.

World: $WORLD
Preset: $PRESET
Setup path: $SETUP_PATH
Log: $LOG_PATH
Note template: $NOTE_PATH

Suggested screenshot command while Gazebo/RViz is open:
  gnome-screenshot -f "$SHOT_DIR/world_${WORLD}_${PRESET}_$(date +%F_%H-%M-%S).png"

EOF

ros2 launch jackal_helper BARN_runner.launch.py   world_idx:=$WORLD   gui:=$GUI   rviz:=$RVIZ   timeout:=$TIMEOUT   throttle_duration:=$THROTTLE   nav2_log_level:=$LOG_LEVEL   setup_path:=$SETUP_PATH   2>&1 | tee "$LOG_PATH"

echo
echo "===== Final summary ====="
grep -nE "Test finished|Navigation succeeded|Navigation timeout|Navigation collided|Navigation metric" "$LOG_PATH" || true

echo
echo "Log saved to: $LOG_PATH"
echo "Note template: $NOTE_PATH"
echo "Screenshots dir: $SHOT_DIR"
