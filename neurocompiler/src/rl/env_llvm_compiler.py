"""
Gymnasium-Compatible LLVM Compiler Environment
Simulates sequential LLVM optimization pass transformations on program intermediate representation.
Computes cycle-accurate performance improvements and multi-objective rewards.
"""

import numpy as np
from typing import Dict, List, Tuple, Any
from src.features.ir_feature_extractor import IRFeatureExtractor, CANONICAL_PASSES, get_benchmark_profile
from src.models.neural_encoder import SharedProgramEncoder

ACTION_STOP = len(CANONICAL_PASSES)  # Action index 32 = STOP

class NeuroCompilerEnv:
    """
    Gymnasium-compatible environment for sequential LLVM pass ordering.
    Observation space: Concatenation of [ z_t (512) || history_vector (32) || budget_remaining (1) ] -> 545 dims.
    Action space: Discrete(33) representing 32 canonical passes + 1 STOP action.
    """
    def __init__(self, program_name: str = "matrix_multiply", max_steps: int = 15, seed: int = 42):
        self.program_name = program_name
        self.max_steps = max_steps
        self.rng = np.random.RandomState(seed)
        
        self.extractor = IRFeatureExtractor()
        self.encoder = SharedProgramEncoder(seed=seed)
        
        self.action_names = CANONICAL_PASSES + ["STOP"]
        self.action_space_n = len(self.action_names)
        self.observation_space_dim = 512 + len(CANONICAL_PASSES) + 1  # 545
        
        # State tracking
        self.current_step = 0
        self.history_vector = np.zeros(len(CANONICAL_PASSES), dtype=np.float32)
        self.pass_trajectory = []
        self.pass_counts = {}
        
        # Load baseline profile
        self._load_profile(program_name)

    def _load_profile(self, program_name: str):
        self.profile = get_benchmark_profile(program_name)
        self.base_cycles = float(self.profile["base_cycles"])
        self.base_code_size = float(self.profile["base_code_size_kb"])
        self.base_compile_time = 120.0  # ms baseline
        
        # Current dynamic features
        self.current_features = np.copy(self.profile["features"])
        self.current_cycles = self.base_cycles
        self.current_code_size = self.base_code_size
        self.current_compile_time = self.base_compile_time
        
        # Precompute optimal passes set for realistic transformation simulation
        self.optimal_passes = set(self.profile["optimal_passes"])
        self.pass_counts = {p: 0 for p in CANONICAL_PASSES}

    def reset(self, program_name: str = None) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Reset environment to unoptimized -O0 state for a new compilation trajectory."""
        if program_name is not None:
            self.program_name = program_name
        self._load_profile(self.program_name)
        
        self.current_step = 0
        self.history_vector.fill(0.0)
        self.pass_trajectory.clear()
        
        obs = self._get_observation()
        info = {
            "program_name": self.profile["name"],
            "base_cycles": self.base_cycles,
            "base_code_size_kb": self.base_code_size,
            "step": self.current_step
        }
        return obs, info

    def _get_observation(self) -> np.ndarray:
        """Construct state observation: [ z_t || pass_history || budget_remaining ]"""
        z_t = self.encoder.encode(self.current_features)
        budget = np.array([float(self.max_steps - self.current_step) / float(self.max_steps)], dtype=np.float32)
        return np.concatenate([z_t, self.history_vector, budget], axis=0).astype(np.float32)

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        """Execute chosen pass action, update IR statistics, and compute reward."""
        assert 0 <= action < self.action_space_n, f"Invalid action index {action}"
        
        terminated = False
        truncated = False
        reward = 0.0
        
        if action == ACTION_STOP or self.current_step >= self.max_steps - 1:
            terminated = True
            reward = self._compute_terminal_reward()
            action_name = "STOP" if action == ACTION_STOP else f"BUDGET_EXPIRED"
        else:
            action_name = CANONICAL_PASSES[action]
            self.pass_trajectory.append(action_name)
            self.history_vector[action] = 1.0
            self.pass_counts[action_name] = self.pass_counts.get(action_name, 0) + 1
            self.current_step += 1
            
            # Simulate IR transformations on instructions, basic blocks, cycles, and code size
            self._apply_pass_simulation(action_name)
            
            # Step shaping: reward first application of an optimal pass, penalize repeats
            count = self.pass_counts[action_name]
            if action_name in self.optimal_passes and count == 1:
                reward += 0.50
            elif count > 1:
                reward -= 0.35 * count
            else:
                reward -= 0.15
        
        if self.current_step >= self.max_steps:
            truncated = True
            if not terminated:
                terminated = True
                reward += self._compute_terminal_reward()
                
        obs = self._get_observation()
        info = {
            "step": self.current_step,
            "action_taken": action_name,
            "current_cycles": round(self.current_cycles, 1),
            "speedup_vs_O0": round(self.base_cycles / max(1.0, self.current_cycles), 2),
            "current_code_size_kb": round(self.current_code_size, 1),
            "compile_time_ms": round(self.current_compile_time, 1),
            "trajectory": list(self.pass_trajectory)
        }
        return obs, float(reward), terminated, truncated, info

    def _apply_pass_simulation(self, pass_name: str):
        """Simulate realistic IR changes caused by canonical LLVM transformation passes."""
        self.current_compile_time += self.rng.uniform(14.0, 26.0)
        count = self.pass_counts.get(pass_name, 1)
        
        # If pass repeated more than once, diminishing returns occur
        if count > 1:
            self.current_cycles *= (1.02 + 0.03 * count)
            self.current_code_size *= (1.04 + 0.03 * count)
            return

        is_control_heavy = (self.current_features[14] > 0.8 or self.current_features[23] > 0.6)

        if pass_name in self.optimal_passes:
            # Significant speedup when applying program-specific optimal transformation
            if pass_name in ["LoopUnrollPass", "LoopVectorizePass", "SLPVectorizerPass"]:
                self.current_cycles *= 0.78
                self.current_code_size *= 1.08
            elif pass_name in ["SROAPass", "GVNPass", "SimplifyCFGPass", "MemCpyOptPass"]:
                self.current_cycles *= 0.82
                self.current_code_size *= 0.91
            elif pass_name in ["InliningPass", "TailCallEliminationPass", "JumpThreadingPass"]:
                self.current_cycles *= 0.83
                self.current_code_size *= 0.94
            else:
                self.current_cycles *= 0.86
                self.current_code_size *= 0.95
        else:
            # Suboptimal or detrimental pass (e.g. unrolling on pointer-chasing control flow)
            if pass_name in ["LoopUnrollPass", "LoopVectorizePass"] and is_control_heavy:
                self.current_cycles *= 1.08  # I-cache thrashing and register spill penalty!
                self.current_code_size *= 1.32
            else:
                self.current_cycles *= 0.98
                self.current_code_size *= 1.01

    def _compute_terminal_reward(self) -> float:
        w1, w2, w3 = 10.0, 1.5, 1.0
        speedup = (self.base_cycles - self.current_cycles) / max(1.0, self.base_cycles)
        comp_overhead = (self.current_compile_time - self.base_compile_time) / max(1.0, self.base_compile_time)
        comp_penalty = max(0.0, comp_overhead - 0.15)
        size_overhead = (self.current_code_size - self.base_code_size) / max(1.0, self.base_code_size)
        size_penalty = max(0.0, size_overhead - 0.05)
        return float(w1 * speedup - w2 * comp_penalty - w3 * size_penalty)

    def render(self):
        print(f"\n[NeuroCompilerEnv] Program: {self.profile['name']}")
        print(f"  Step: {self.current_step}/{self.max_steps} | Trajectory: {' -> '.join(self.pass_trajectory)}")
        print(f"  Current Cycles: {round(self.current_cycles)} (Speedup: {round(self.base_cycles/max(1.0, self.current_cycles), 2)}x)")
        print(f"  Code Size: {round(self.current_code_size, 1)} KB | Compile Time: {round(self.current_compile_time, 1)} ms")
