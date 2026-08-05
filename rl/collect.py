"""Expert transition collection, across processes (doc 99 entry 48).

Behaviour cloning's 39-minute median was almost entirely *serial episode
collection*. Profiling put the fitting loop at roughly one minute of that, the
observation encoder at 0.3% of wall clock and the torch forward at 1.2%; 97.8%
of ``env.step`` is inside :meth:`CombatSimulator.run`. So the task is not slow
because of anything clever -- it is one core simulating fights while eleven sit
idle.

Episodes are independent: :meth:`TFTEnv.reset` builds a fresh ``Match`` from the
seed, and the only process-global state is the uid counter in
:mod:`engine.unit`, whose *relative* order within a fight is what determinism
depends on. That was verified rather than assumed -- one seed collected alone in
a fresh process, after a decoy episode so the counter starts at a different
offset, reproduces the same observations, masks, actions and returns as the same
seed collected mid-batch.

The workers live here rather than in ``scripts/train_ppo.py`` deliberately. Under
``spawn`` a worker function defined in a ``__main__`` script forces every child
to re-import ``__main__``; a module keeps that off the table entirely.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from rl.env import TFTEnv
from rl.evaluate import scripted_policy

_WORKER: dict = {}


def discounted_returns(rewards: Sequence[float], gamma: float) -> list[float]:
    """Discounted return at each step, accumulated backwards from the terminal.

    ``G_t = r_t + gamma * G_{t+1}``, with ``G_T = r_T``. Computed per episode:
    letting returns bleed across an episode boundary would credit one game's
    reward to another's states, which is the classic way to poison a value
    target without it being visible in the loss curve.
    """
    running = 0.0
    out = [0.0] * len(rewards)
    for i in range(len(rewards) - 1, -1, -1):
        running = rewards[i] + gamma * running
        out[i] = running
    return out


def collect_episode(env, policy, seed: int, gamma: float, actor=None):
    """One episode of ``(observation, mask, expert action, return)``.

    Shared by the serial and parallel paths so the two cannot drift apart. The
    expert labels every state *before* the step, whoever is driving.
    """
    obs, _ = env.reset(seed=seed)
    observations, masks, actions, rewards = [], [], [], []
    terminated = False
    while not terminated:
        mask = env.action_mask()
        observations.append(obs.copy())
        masks.append(mask.copy())
        actions.append(policy(obs, mask))
        obs, reward, terminated, _, _ = env.step(
            actions[-1] if actor is None else actor(obs, mask)
        )
        rewards.append(float(reward))
    return observations, masks, actions, discounted_returns(rewards, gamma)


def _init(data_dir, env_kwargs: dict, expert_kwargs: dict,
          search_kwargs: dict | None = None) -> None:
    import logging

    from engine.loader import load_all

    # Each worker re-loads the dataset and would otherwise re-emit the loader's
    # unverified-constants warning, once per process.
    logging.getLogger("engine.loader").setLevel(logging.ERROR)
    data = load_all(data_dir) if data_dir is not None else load_all()
    env = TFTEnv(data=data, **env_kwargs)
    _WORKER["env"] = env
    policy = scripted_policy(env, **expert_kwargs)
    if search_kwargs is not None:
        from rl.search import search_policy

        # A teacher that repositions. 52.4 found the scripted policy issues
        # zero board-slot SELECTs -- it places a unit once and never moves it --
        # so the whole positional axis is unexploited by the incumbent.
        policy = search_policy(env, base=policy, **search_kwargs)
    _WORKER["policy"] = policy


def _episode(job):
    seed, gamma = job
    obs, masks, actions, returns = collect_episode(
        _WORKER["env"], _WORKER["policy"], seed, gamma
    )
    return seed, np.array(obs), np.array(masks), np.array(actions), np.array(returns)


def collect_parallel(
    seeds: Sequence[int],
    gamma: float,
    workers: int | None = None,
    data_dir=None,
    env_kwargs: dict | None = None,
    expert_kwargs: dict | None = None,
    search_kwargs: dict | None = None,
):
    """Collect expert transitions over ``seeds`` across processes.

    Blocks are concatenated in **seed order**, not completion order, so the
    dataset is byte-for-byte what the serial path produces. That matters more
    here than it does for evaluation: row order sets the minibatch composition
    during fitting, so a completion-ordered dataset would silently make cloning
    unreproducible even though every individual row was correct.

    ``actor`` has no parallel path on purpose. Plain behaviour cloning -- the
    39-minute case -- needs nothing in the worker but the scripted policy, while
    a DAgger actor is a torch model that would have to be shipped to each worker
    and re-shipped every round. That is a separate change; the caller falls back
    to serial when an actor is present.
    """
    import multiprocessing as mp

    seeds = list(seeds)
    env_kwargs = env_kwargs or {}
    expert_kwargs = expert_kwargs or {}
    workers = workers or mp.cpu_count()

    jobs = [(seed, gamma) for seed in seeds]
    context = mp.get_context("spawn")
    with context.Pool(
        processes=workers,
        initializer=_init,
        initargs=(data_dir, env_kwargs, expert_kwargs, search_kwargs),
    ) as pool:
        # imap_unordered for the same reason evaluation uses it: games run from
        # ~3 to ~10 seconds, so returning blocks as they finish keeps every
        # worker busy. Results therefore arrive out of order, which is why the
        # reassembly below is keyed by seed rather than zipped positionally.
        rows = list(pool.imap_unordered(_episode, jobs))

    by_seed = {seed: block for seed, *block in rows}
    observations, masks, actions, returns = [], [], [], []
    for seed in seeds:
        block_obs, block_masks, block_actions, block_returns = by_seed[seed]
        observations.append(block_obs)
        masks.append(block_masks)
        actions.append(block_actions)
        returns.append(block_returns)
    return (
        np.concatenate(observations),
        np.concatenate(masks),
        np.concatenate(actions),
        np.concatenate(returns).astype(np.float32),
    )
