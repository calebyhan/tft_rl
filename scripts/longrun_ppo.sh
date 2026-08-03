#!/bin/bash
# Milestone 13 follow-up: does the low-LR arm hold, or is it just slower?
#
# The screen (doc 99 23) found learning rate dominant: 5e-5 recovered 83% of
# the degradation, t=-3.21. The objection it cannot answer is that a policy
# taking 1/6-size steps over 60k steps barely moves, and a policy that barely
# moves trivially keeps its warm start. Duration is what separates the two
# readings: if it is only slowness, this degrades like the control, just later.
#
# --target-kl runs alongside because it restrains drift WITHOUT throttling
# learning -- the arm that could produce a gain rather than an avoided loss.
#
# NOTE the seed differs from the screen's. The screen chose these arms; scoring
# them on the seed that chose them would be selection bias.
set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python
COMMON="--warm-start 400 --warm-start-epochs 50 --reward-shaping \
        --eval-episodes 300 --eval-every 25000 --timesteps 250000 \
        --seed 21 --envs 3 --device cpu"

run () {
  local name=$1; shift
  echo "=== $name : starting $(date +%H:%M:%S) ==="
  $PY scripts/train_ppo.py $COMMON --run-dir "runs/$name" "$@" \
    > "runs/$name.log" 2>&1
  echo "=== $name : done $(date +%H:%M:%S) rc=$? ==="
}

mkdir -p runs

run f13_control &                              # does it keep climbing at 250k?
run f13_lowlr --learning-rate 5e-5 &           # holds, or degrades late?
run f13_kl    --target-kl 0.02 &               # leash without the throttle
wait

echo "=== LONG RUN DONE $(date +%H:%M:%S) ==="
