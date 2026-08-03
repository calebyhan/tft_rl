#!/bin/bash
# Milestone 14: does DAgger close the imitation gap?
#
# The clone matches the scripted expert's action 81.7% of the time yet places
# 1.29 worse than it -- the signature of compounding off-policy drift, which
# DAgger is the textbook fix for (doc 99 22, open item 3).
#
# BUDGET-MATCHED BY DESIGN. DAgger adds labelled data, so a naive
# "BC 400 vs BC 400 + 3x100 DAgger" would confound the method with 300 extra
# episodes and let a pure data effect look like a distribution-shift fix. The
# control is BC at 700, the same total label budget. The question is whether it
# matters *where* the states come from, not how many there are.
#
# No PPO phase anywhere: this is a question about the clone.
set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python
COMMON="--timesteps 0 --warm-start-epochs 50 --reward-shaping \
        --eval-episodes 300 --seed 21 --envs 3 --device cpu"

run () {
  local name=$1; shift
  echo "=== $name : starting $(date +%H:%M:%S) ==="
  $PY scripts/train_ppo.py $COMMON --run-dir "runs/$name" "$@" \
    > "runs/$name.log" 2>&1
  echo "=== $name : done $(date +%H:%M:%S) rc=$? ==="
}

mkdir -p runs

run m14_bc400  --warm-start 400 &                              # reference point
run m14_bc700  --warm-start 700 &                              # budget-matched control
run m14_dagger --warm-start 400 --dagger-rounds 3 --dagger-episodes 100 &
wait

echo "=== DAGGER A/B DONE $(date +%H:%M:%S) ==="
