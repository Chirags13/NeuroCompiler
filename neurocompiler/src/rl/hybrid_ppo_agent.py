"""
Hybrid PPO Agent with Action Space Pruning
Couples Supervised Pass Profitability predictions (Model A) with Proximal Policy Optimization (PPO).
Dynamically prunes the combinatorial 33-action space down to only the Top-K most viable passes (plus STOP) at each step.
"""

import numpy as np
from typing import Dict, List, Tuple, Any, Set
from src.features.ir_feature_extractor import CANONICAL_PASSES
from src.models.neural_encoder import SharedProgramEncoder
from src.models.supervised_heads import SupervisedMultiHead
from src.rl.env_llvm_compiler import ACTION_STOP

class HybridPPOAgent:
    """
    Hybrid RL orchestrator incorporating Supervised Action Pruning.
    Pruning threshold tau = 0.30, Top-K = 8.
    """
    def __init__(self, action_dim: int = 33, top_k: int = 8, tau: float = 0.30, seed: int = 42):
        self.action_dim = action_dim
        self.top_k = top_k
        self.tau = tau
        self.rng = np.random.RandomState(seed)
        
        self.encoder = SharedProgramEncoder(seed=seed)
        self.supervised_head = SupervisedMultiHead(latent_dim=512, seed=seed)
        
        # Policy network weights
        self.W_policy = self.rng.normal(0.0, 0.05, (545, action_dim)).astype(np.float32)
        self.b_policy = np.zeros(action_dim, dtype=np.float32)
        
        # Experience replay buffer for policy gradient updates
        self.memory = []

    def select_action(self, obs: np.ndarray, current_features: np.ndarray = None, explore: bool = True) -> Tuple[int, Dict[str, Any]]:
        """
        Select an optimization pass action via Hybrid Action Space Pruning.
        1. Query Model A (Supervised Pass Profitability Head) on current state embedding z_t.
        2. Prune action space to Top-K candidates where P > tau, plus STOP action.
        3. Filter out passes that have already been applied in this trajectory (from history vector obs[512:512+32]).
        4. Sample (explore=True) or select argmax/optimal unvisited pass (explore=False).
        """
        # Extract d=512 latent embedding and history vector
        z_t = obs[:512]
        history_vector = obs[512:512 + len(CANONICAL_PASSES)]
        
        # 1. Query Supervised Pass Profitability
        sl_preds = self.supervised_head.predict_all(z_t, raw_features=current_features)
        prof_probs = sl_preds["pass_profitability_probs"]
        
        # 2. Prune Action Space
        sorted_indices = np.argsort(prof_probs)[::-1]
        pruned_actions: List[int] = []
        
        for idx in sorted_indices:
            if len(pruned_actions) >= self.top_k:
                break
            # Skip pass if already applied in history vector to prevent loop thrashing
            if history_vector[idx] > 0.5:
                continue
            if prof_probs[idx] > self.tau or len(pruned_actions) < 3:
                pruned_actions.append(int(idx))
                
        # Always include STOP action
        if ACTION_STOP not in pruned_actions:
            pruned_actions.append(ACTION_STOP)
            
        # If no unvisited candidate pass has probability > 0.45, trigger STOP to prevent degradation!
        unvisited_top_prob = max([prof_probs[a] for a in pruned_actions if a < len(CANONICAL_PASSES)], default=0.0)
        if not explore and unvisited_top_prob < 0.48:
            return ACTION_STOP, {
                "pruned_candidate_count": len(pruned_actions),
                "top_candidates": [("STOP", 1.0)],
                "selected_action": "STOP",
                "action_prob": 1.0
            }

        # 3. Compute policy logits and apply probability mask
        logits = np.dot(obs, self.W_policy) + self.b_policy
        masked_logits = np.full(self.action_dim, -1e9, dtype=np.float32)
        
        for act in pruned_actions:
            prior_boost = 3.5 * prof_probs[act] if act < len(prof_probs) else 0.2
            if act < len(CANONICAL_PASSES) and history_vector[act] > 0.5:
                prior_boost -= 4.0
            masked_logits[act] = logits[act] + prior_boost
            
        exp_l = np.exp(masked_logits - np.max(masked_logits))
        probs = exp_l / np.sum(exp_l)
        
        if explore:
            action = int(self.rng.choice(self.action_dim, p=probs))
        else:
            # Deterministic inference selects top unvisited profitable candidate
            valid_acts = [a for a in pruned_actions if a < len(CANONICAL_PASSES)]
            if valid_acts:
                action = int(max(valid_acts, key=lambda a: prof_probs[a]))
            else:
                action = ACTION_STOP
            
        info = {
            "pruned_candidate_count": len(pruned_actions),
            "top_candidates": [(CANONICAL_PASSES[a] if a < len(CANONICAL_PASSES) else "STOP", round(float(prof_probs[a] if a < len(prof_probs) else 1.0), 3)) for a in pruned_actions[:4]],
            "selected_action": CANONICAL_PASSES[action] if action < len(CANONICAL_PASSES) else "STOP",
            "action_prob": round(float(probs[action]), 3)
        }
        return action, info

    def store_step(self, obs: np.ndarray, action: int, reward: float, next_obs: np.ndarray, done: bool):
        self.memory.append((obs, action, reward, next_obs, done))

    def update_policy(self, lr: float = 0.01):
        if not self.memory:
            return
        
        returns = []
        G = 0.0
        for _, _, r, _, done in reversed(self.memory):
            if done:
                G = 0.0
            G = r + 0.95 * G
            returns.insert(0, G)
            
        returns = np.array(returns, dtype=np.float32)
        if len(returns) > 1 and np.std(returns) > 1e-5:
            returns = (returns - np.mean(returns)) / (np.std(returns) + 1e-6)
            
        for (obs, action, _, _, _), G_norm in zip(self.memory, returns):
            logits = np.dot(obs, self.W_policy) + self.b_policy
            exp_l = np.exp(logits - np.max(logits))
            probs = exp_l / np.sum(exp_l)
            
            d_logits = -probs
            d_logits[action] += 1.0
            
            self.W_policy += lr * np.outer(obs, d_logits) * G_norm
            self.b_policy += lr * d_logits * G_norm
            
        self.memory.clear()
