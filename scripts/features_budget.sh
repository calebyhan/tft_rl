#!/bin/bash
# Milestone 16: is BUY an information problem or a structural one? (doc 99 26.3)
#
# BUY sits at 45.9%-53.0% against a measured ceiling of 90.7% (26.1) and is the
# only action kind that ignores data and distribution alike. Entry 25.2 blamed
# the observation: under champion_encoding=index a shop slot is 2 floats and
# cannot express what the champion would contribute to a trait.
#
# The 400-episode features arm could not test that -- 2056 dims on a
# 400-episode budget overfit uniformly, degrading every action kind (26.2). The
# fix is to scale labels with dimensionality.
#
# The index arm at the same budget is the control that matters: it separates
# "more data helps BUY" from "trait information helps BUY". Without it, any
# improvement is unattributable.
#
# Dependent variable is BUY match against the 90.7% ceiling, NOT placement.
set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python
COMMON="--timesteps 0 --warm-start 1500 --warm-start-epochs 50 --reward-shaping \
        --eval-episodes 300 --seed 21 --envs 3 --device cpu"

run () {
  local name=$1; shift
  echo "=== $name : starting $(date +%H:%M:%S) ==="
  $PY scripts/train_ppo.py $COMMON --run-dir "runs/$name" "$@" \
    > "runs/$name.log" 2>&1
  echo "=== $name : done $(date +%H:%M:%S) rc=$? ==="
}

mkdir -p runs

run m16_features1500 --champion-encoding features &
run m16_index1500    --champion-encoding index &
wait

echo "=== BUDGET ARMS DONE $(date +%H:%M:%S) ==="

for arm in m16_features1500 m16_index1500; do
  enc=index; [[ $arm == *features* ]] && enc=features
  echo "=== per-kind match: $arm ($enc) ==="
  $PY scripts/action_match.py "runs/$arm/model.zip" \
      --champion-encoding "$enc" --episodes 20 2>&1 | grep -A 22 "=== runs"
done
