#!/bin/bash
# Milestone 19: PPO and self-play, re-tested from a clone at teacher parity.
#
# Every PPO result in doc 99 22-23 was measured against a warm start that
# placed 5.8-5.9 and made a coin-flip decision on BUY. The clone now places
# 4.567 against a 4.620 teacher (entry 30), so those verdicts describe a
# different policy and none of them transfer.
#
# 19.2 set the precondition explicitly: self-play is "worth revisiting only
# once the agent is at or past the scripted baseline, which is the condition
# under which fixed opponents become the binding constraint." That is now true.
#
# It is also the only remaining route past 4.620 -- imitation caps at the
# teacher by construction, and the clone is already there.
#
# ppo_nokl is not optional bookkeeping: --target-kl 0.02 became the *default*
# on evidence from a degrading run (23.5). If the degradation was an artefact
# of the weak clone, that default is now unjustified.
set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python
COMMON="--warm-start 400 --warm-start-epochs 50 --reward-shaping \
        --eval-episodes 300 --eval-every 30000 --seed 21 --envs 3 --device cpu"

run () {
  local name=$1; shift
  echo "=== $name : starting $(date +%H:%M:%S) ==="
  $PY scripts/train_ppo.py $COMMON --run-dir "runs/$name" "$@" \
    > "runs/$name.log" 2>&1
  echo "=== $name : done $(date +%H:%M:%S) rc=$? ==="
}

mkdir -p runs

run m19_ppo      --timesteps 120000 &
run m19_nokl     --timesteps 120000 --target-kl 0 &
run m19_selfplay --timesteps 120000 --self-play &
wait

echo "=== PARITY ARMS DONE $(date +%H:%M:%S) ==="
