"""RL upgrade (Phase 8): PPO over macro-actions, rewarded by the surrogate.

Only worth running if the surrogate passed gate 7B, and only kept if it beats the plain top-k
loop and a GA at equal compile budget (nc.evaluate compares them).

State   = program features (standardized, from training programs) + encoding of the current genome
Actions = macro-edits (pruned knowledge-base actions if available, else v2 family edits, knobs and
          llc levels) + STOP; an action already taken is masked
Episode = up to H edits starting from -O3; reward = surrogate(g_t+1) - surrogate(g_t), so the
          return is the predicted log speedup of the final genome over -O3.
Policy and value are one-hidden-layer MLPs written in numpy (no torch dependency); Adam.
"""
from __future__ import annotations

import json
import math
import random
import time
from pathlib import Path

import numpy as np

from .features import encode_genome
from .pipeline import Genome, Space


def macro_actions(space: Space, results_dir: Path, max_actions: int = 120) -> list[dict]:
    acts: list[dict] = []
    p = results_dir / "passkb_actions.json"
    if p.exists():
        acts = [a["edit"] for a in json.loads(p.read_text())["actions"]][:max_actions]
    if len(acts) < 20:
        seen = set()
        for f in space.params:
            k = (f["pass"], f["tok"], f["new"])
            if k not in seen:
                seen.add(k)
                acts.append({"op": "param_all", "pass": f["pass"], "tok": f["tok"], "new": f["new"]})
        acts += [{"op": "del_all", "pass": n} for n in space.multi]
        for k, vs in space.knobs.items():
            acts += [{"op": "knob", "name": k, "value": v} for v in vs]
        acts += [{"op": "backend", "value": b} for b in (1, 2)]
    return acts[:max_actions]


class MLP:
    def __init__(self, n_in, n_hid, n_out, rng, scale=1.0):
        self.W1 = rng.normal(0, 1 / math.sqrt(n_in), (n_in, n_hid))
        self.b1 = np.zeros(n_hid)
        self.W2 = rng.normal(0, scale / math.sqrt(n_hid), (n_hid, n_out))
        self.b2 = np.zeros(n_out)
        self.params = [self.W1, self.b1, self.W2, self.b2]
        self.m = [np.zeros_like(p) for p in self.params]
        self.v = [np.zeros_like(p) for p in self.params]
        self.t = 0

    def forward(self, X):
        H = np.tanh(X @ self.W1 + self.b1)
        return H, H @ self.W2 + self.b2

    def backward(self, X, H, dOut):
        gW2 = H.T @ dOut
        gb2 = dOut.sum(0)
        dH = dOut @ self.W2.T * (1 - H ** 2)
        return [X.T @ dH, dH.sum(0), gW2, gb2]

    def adam(self, grads, lr, b1=0.9, b2=0.999, eps=1e-8, clip=1.0):
        norm = math.sqrt(sum(float((g ** 2).sum()) for g in grads))
        if norm > clip:
            grads = [g * clip / norm for g in grads]
        self.t += 1
        for i, (p, g) in enumerate(zip(self.params, grads)):
            self.m[i] = b1 * self.m[i] + (1 - b1) * g
            self.v[i] = b2 * self.v[i] + (1 - b2) * g * g
            mh = self.m[i] / (1 - b1 ** self.t)
            vh = self.v[i] / (1 - b2 ** self.t)
            p -= lr * mh / (np.sqrt(vh) + eps)


class PassEnv:
    def __init__(self, surrogate, names: dict[int, str], actions: list[dict], pfeats: dict[str, dict],
                 horizon: int = 4):
        self.s, self.names, self.actions, self.H = surrogate, names, actions, horizon
        self.pf = pfeats
        prog_names = surrogate.fnames[:surrogate.np]
        P = np.array([[d.get(k, np.nan) for k in prog_names] for d in pfeats.values()], float)
        self.mu, self.sd = np.nanmean(P, 0), np.nanstd(P, 0) + 1e-9
        self.prog_names = prog_names
        self.enc_names = sorted(encode_genome(Genome([]), names))
        self.n_obs = len(prog_names) + len(self.enc_names) + 1
        self.n_act = len(actions) + 1          # last = STOP
        self._cache: dict[tuple, float] = {}

    def score(self, pid: str, g: Genome) -> float:
        k = (pid, g.to_json())
        if k not in self._cache:
            self._cache[k] = float(self.s.predict(self.pf[pid], [g], self.names)[0])
        return self._cache[k]

    def obs(self, pid: str, g: Genome, t: int) -> np.ndarray:
        p = np.nan_to_num((np.array([self.pf[pid].get(k, np.nan) for k in self.prog_names]) - self.mu) / self.sd)
        e = encode_genome(g, self.names)
        return np.concatenate([np.clip(p, -5, 5), [math.tanh(e[k] / 4) for k in self.enc_names], [t / self.H]])


def _softmax_masked(logits, mask):
    z = np.where(mask, logits, -1e9)
    z = z - z.max(-1, keepdims=True)
    e = np.exp(z) * mask
    return e / e.sum(-1, keepdims=True)


def train_ppo(env: PassEnv, programs: list[str], iters: int = 60, episodes: int = 32, seed: int = 0,
              lr: float = 3e-3, clip: float = 0.2, ent: float = 0.01, epochs: int = 4, log=print) -> dict:
    rng = np.random.default_rng(seed)
    prng = random.Random(seed)
    pi = MLP(env.n_obs, 64, env.n_act, rng, scale=0.01)
    vf = MLP(env.n_obs, 64, 1, rng)
    hist = []
    for it in range(iters):
        O, A, M, R, LP, V, ADV = [], [], [], [], [], [], []
        ep_ret = []
        for _ in range(episodes):
            pid = prng.choice(programs)
            g, used, t = Genome([]), set(), 0
            prev = env.score(pid, g)
            traj = []
            while True:
                o = env.obs(pid, g, t)
                mask = np.ones(env.n_act, bool)
                for u in used:
                    mask[u] = False
                if t >= env.H:
                    mask[:-1] = False
                _, logits = pi.forward(o[None])
                p = _softmax_masked(logits, mask[None])[0]
                a = int(rng.choice(env.n_act, p=p))
                v = float(vf.forward(o[None])[1][0, 0])
                if a == env.n_act - 1:
                    traj.append((o, a, mask, 0.0, math.log(p[a] + 1e-12), v))
                    break
                e = dict(env.actions[a])
                if e.get("op") == "ins":
                    e["nid"] = 800000000 + it * 10000 + len(g.edits)
                g = Genome(g.edits + [e])
                cur = env.score(pid, g)
                traj.append((o, a, mask, cur - prev, math.log(p[a] + 1e-12), v))
                prev, t = cur, t + 1
                used.add(a)
            # GAE (gamma = 1, lambda = 0.95)
            adv, last = [0.0] * len(traj), 0.0
            for i in reversed(range(len(traj))):
                nv = traj[i + 1][5] if i + 1 < len(traj) else 0.0
                delta = traj[i][3] + nv - traj[i][5]
                last = delta + 0.95 * last
                adv[i] = last
            for (o, a, mask, r, lp, v), ad in zip(traj, adv):
                O.append(o), A.append(a), M.append(mask), R.append(ad + v), LP.append(lp), V.append(v), ADV.append(ad)
            ep_ret.append(sum(x[3] for x in traj))
        O, A, M = np.array(O), np.array(A), np.array(M)
        RET, LP0, ADV = np.array(R), np.array(LP), np.array(ADV)
        ADV = (ADV - ADV.mean()) / (ADV.std() + 1e-8)
        n = len(A)
        for _ in range(epochs):
            idx = rng.permutation(n)
            for s in range(0, n, 64):
                b = idx[s:s + 64]
                H, logits = pi.forward(O[b])
                P = _softmax_masked(logits, M[b])
                lp = np.log(P[np.arange(len(b)), A[b]] + 1e-12)
                ratio = np.exp(lp - LP0[b])
                adv = ADV[b]
                use = ((ratio < 1 + clip) | (adv < 0)) & ((ratio > 1 - clip) | (adv > 0))
                # d(-min(r*A, clip(r)*A))/dlogits = -A*r*(onehot - P) where unclipped
                coef = -(adv * ratio * use)[:, None]
                onehot = np.zeros_like(P)
                onehot[np.arange(len(b)), A[b]] = 1
                d = coef * (onehot - P)
                # entropy bonus gradient: -ent * dH/dlogits, H = -sum P log P
                logP = np.log(P + 1e-12)
                Hent = -(P * logP).sum(1, keepdims=True)
                d += ent * P * (logP + Hent)
                d *= M[b]
                pi.adam(pi.backward(O[b], H, d / len(b)), lr)
                Hv, vout = vf.forward(O[b])
                dv = (vout[:, 0] - RET[b])[:, None] / len(b)
                vf.adam(vf.backward(O[b], Hv, dv), lr)
        hist.append(float(np.mean(ep_ret)))
        if it % 10 == 0 or it == iters - 1:
            log(f"  ppo iter {it:>3d}: mean predicted return {hist[-1]:+.4f} (log speedup), episodes {episodes}")
    return {"pi": pi, "vf": vf, "history": hist}


def propose(env: PassEnv, pi: MLP, pid: str, n: int, seed: int = 0, greedy_first: bool = True) -> list[Genome]:
    rng = np.random.default_rng(seed)
    out, seen = [], set()
    for ep in range(n * 4):
        g, used, t = Genome([]), set(), 0
        while True:
            o = env.obs(pid, g, t)
            mask = np.ones(env.n_act, bool)
            for u in used:
                mask[u] = False
            if t >= env.H:
                mask[:-1] = False
            p = _softmax_masked(pi.forward(o[None])[1], mask[None])[0]
            a = int(np.argmax(p)) if (greedy_first and ep == 0) else int(rng.choice(env.n_act, p=p))
            if a == env.n_act - 1:
                break
            e = dict(env.actions[a])
            if e.get("op") == "ins":
                e["nid"] = 700000000 + ep * 100 + t
            g = Genome(g.edits + [e])
            used.add(a)
            t += 1
        k = g.to_json()
        if g.edits and k not in seen:
            seen.add(k)
            out.append(g)
        if len(out) >= n:
            break
    return sorted(out, key=lambda g: -env.score(pid, g))


def save_policy(path: Path, out: dict, env: PassEnv, meta: dict) -> None:
    pi = out["pi"]
    np.savez(path, W1=pi.W1, b1=pi.b1, W2=pi.W2, b2=pi.b2, mu=env.mu, sd=env.sd)
    path.with_suffix(".json").write_text(json.dumps({**meta, "actions": env.actions, "horizon": env.H,
                                                     "history": out["history"],
                                                     "created": time.strftime("%Y%m%d-%H%M%S")}, indent=1))


def load_policy(path: Path, env: PassEnv) -> MLP:
    d = np.load(path)
    pi = MLP(env.n_obs, d["W1"].shape[1], env.n_act, np.random.default_rng(0))
    pi.W1[...], pi.b1[...], pi.W2[...], pi.b2[...] = d["W1"], d["b1"], d["W2"], d["b2"]
    return pi
