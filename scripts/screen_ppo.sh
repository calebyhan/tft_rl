#!/bin/bash
# Milestone 13 screen: why does PPO degrade its own behaviour-cloned warm start?
#
# Doc 99 22.1 establishes the effect (+0.620 placement worse than BC, t=3.97,
# monotone across twelve checkpoints). This is a SCREEN, not a measurement:
# 60k steps, one seed, n=200. The degradation is plainly visible by 30k, so
# 60k is enough to see which knob flattens the curve at half the cost.
#
# Whatever wins here earns a real 120k / 3-seed / n=300 run. A screen at one
# seed cannot rank two close arms -- that is a tie for replication to break.
set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python
COMMON="--warm-start 400 --warm-start-epochs 50 --eval-episodes 200 \
        --timesteps 60000 --seed 13 --envs 3 --device cpu"

run () {
  local name=$1; shift
  echo "=== $name : starting $(date +%H:%M:%S) ==="
  $PY scripts/train_ppo.py $COMMON --run-dir "runs/$name" "$@" \
    > "runs/$name.log" 2>&1
  echo "=== $name : done $(date +%H:%M:%S) rc=$? ==="
}

mkdir -p runs

# All five share the same 400/50 clone (same seed), so they differ by exactly
# one knob. --reward-shaping is on everywhere except the noshape arm.
run s13_control --reward-shaping &
run s13_noshape &
run s13_kl      --reward-shaping --target-kl 0.02 &
wait
run s13_lowlr   --reward-shaping --learning-rate 5e-5 &
run s13_noent   --reward-shaping --ent-coef 0.0 &
wait

echo "=== SCREEN DONE $(date +%H:%M:%S) ==="
