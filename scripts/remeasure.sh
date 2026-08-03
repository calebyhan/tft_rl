#!/bin/bash
# Milestone 12: one clean measurement pass against the frozen engine.
#
# Every agent number in this repo was measured before items, real PvE combat
# and the Realm draft existed (README "baseline invalidated five times").
# This re-runs the four arms that matter, all sharing the same warm start, so
# the milestone 9 verdicts become quotable again.
#
# Arms are paired: same seed, same 400/50 behaviour-clone, one flag apart.
set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python
COMMON="--warm-start 400 --warm-start-epochs 50 --reward-shaping --eval-episodes 300 --seed 12 --envs 4 --device cpu"

run () {  # name, extra flags
  local name=$1; shift
  echo "=== $name : starting $(date +%H:%M:%S) ==="
  $PY scripts/train_ppo.py $COMMON --run-dir "runs/$name" "$@" \
    > "runs/$name.log" 2>&1
  echo "=== $name : done $(date +%H:%M:%S) rc=$? ==="
}

mkdir -p runs

# Fresh scripted/random baselines first -- cheap, and everything else is read
# relative to them.
echo "=== baselines : starting $(date +%H:%M:%S) ==="
$PY scripts/train_ppo.py --baseline-only --eval-episodes 300 --seed 12 \
  > runs/m12_baselines.log 2>&1
echo "=== baselines : done $(date +%H:%M:%S) ==="

# Pair 1: does PPO beat its own warm start on the finished game?
run m12_bc   --timesteps 0 &
run m12_ppo  --timesteps 120000 &
wait

# Pair 2: the two milestone 9 A/Bs, re-run against the same control (m12_ppo).
run m12_scout    --timesteps 120000 --scouting full &
run m12_selfplay --timesteps 120000 --self-play &
wait

echo "=== ALL DONE $(date +%H:%M:%S) ==="
