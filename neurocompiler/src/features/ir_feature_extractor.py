"""
LLVM IR Feature Extractor
Extracts 25-dimensional statistical and topological representations from LLVM Intermediate Representation (.ll strings or profiles).
"""

import re
import numpy as np
from typing import Dict, List, Union

# Canonical list of 32 LLVM optimization passes managed by NeuroCompiler
CANONICAL_PASSES = [
    "InstCombinePass", "GVNPass", "LICMPass", "LoopUnrollPass", "LoopRotatePass",
    "LoopVectorizePass", "SLPVectorizerPass", "SROAPass", "SimplifyCFGPass",
    "MemCpyOptPass", "SCCPPass", "DeadCodeEliminationPass", "ADCEPass",
    "AggressiveInstCombinePass", "LoopIdiomRecognizePass", "JumpThreadingPass",
    "CorrelatedValuePropagationPass", "TailCallEliminationPass", "ReassociatePass",
    "LoopSinkPass", "LoopDeletionPass", "IndVarSimplifyPass", "LoopDistributePass",
    "LoopLoadEliminationPass", "SpeculativeExecutionPass", "LowerExpectIntrinsicPass",
    "InliningPass", "GlobalDCEPass", "ConstraintEliminationPass", "LoopInterchangePass",
    "WarnMissedTransformationsPass", "RedundantDbgInstEliminationPass"
]

class IRFeatureExtractor:
    """
    Extracts a 25-dimensional numeric feature vector from LLVM IR strings or basic statistics.
    
    Features:
    [0..3]:   Instruction count, Basic block count, Function count, Avg BB size
    [4..9]:   ALU ratio, Logical ratio, Memory ratio, Branch ratio, PHI ratio, Vector ratio
    [10..13]: Load/Store ratio, Alloca count, GEP density, Memory-to-ALU ratio
    [14..17]: Conditional branch density, Unconditional branch ratio, Call density, FP instruction ratio
    [18..21]: Loop count, Max loop depth, Avg basic blocks per loop, Induction variable density
    [22..24]: Cyclomatic complexity index, Register spill vulnerability index, Parallelization index
    """
    def __init__(self):
        self.feature_names = [
            "total_instructions", "basic_blocks", "function_count", "avg_bb_size",
            "alu_ratio", "logical_ratio", "memory_ratio", "branch_ratio", "phi_ratio", "vector_ratio",
            "load_store_ratio", "alloca_count", "gep_density", "memory_to_alu_ratio",
            "cond_branch_density", "uncond_branch_ratio", "call_density", "fp_ratio",
            "loop_count", "max_loop_depth", "avg_bb_per_loop", "induction_var_density",
            "cyclomatic_complexity", "register_spill_vulnerability", "parallelization_index"
        ]
        assert len(self.feature_names) == 25, "Must maintain exactly 25 canonical features."

    def extract_from_ir_string(self, ir_code: str) -> np.ndarray:
        """Parse raw LLVM assembly code (.ll text) into 25 normalized features."""
        lines = [line.strip() for line in ir_code.split('\n') if line.strip() and not line.strip().startswith(';')]
        
        func_count = sum(1 for line in lines if line.startswith('define '))
        bb_count = sum(1 for line in lines if re.match(r'^[a-zA-Z0-9_$.]+:\s*(;.*)?$', line)) or 1
        
        # Instruction matching
        alu_ops = sum(1 for line in lines if any(op in line for op in [' add ', ' sub ', ' mul ', ' sdiv ', ' udiv ', ' srem ']))
        logical_ops = sum(1 for line in lines if any(op in line for op in [' and ', ' or ', ' xor ', ' shl ', ' lshr ', ' ashr ']))
        load_ops = sum(1 for line in lines if ' load ' in line)
        store_ops = sum(1 for line in lines if ' store ' in line)
        alloca_ops = sum(1 for line in lines if ' alloca ' in line)
        gep_ops = sum(1 for line in lines if ' getelementptr ' in line)
        br_cond = sum(1 for line in lines if ' br i1 ' in line)
        br_uncond = sum(1 for line in lines if re.search(r'\bbr label\b', line))
        phi_ops = sum(1 for line in lines if ' phi ' in line)
        call_ops = sum(1 for line in lines if ' call ' in line or ' invoke ' in line)
        fp_ops = sum(1 for line in lines if any(op in line for op in [' fadd ', ' fsub ', ' fmul ', ' fdiv ', ' fcmp ']))
        vec_ops = sum(1 for line in lines if '<' in line and ' x ' in line and '>' in line)
        
        total_insts = max(1, alu_ops + logical_ops + load_ops + store_ops + alloca_ops + gep_ops + br_cond + br_uncond + phi_ops + call_ops + fp_ops)
        
        # Derived metrics
        avg_bb_size = total_insts / max(1, bb_count)
        alu_ratio = alu_ops / total_insts
        logical_ratio = logical_ops / total_insts
        memory_ratio = (load_ops + store_ops + alloca_ops + gep_ops) / total_insts
        branch_ratio = (br_cond + br_uncond) / total_insts
        phi_ratio = phi_ops / total_insts
        vector_ratio = vec_ops / total_insts
        
        ls_ratio = load_ops / max(1, store_ops)
        gep_density = gep_ops / total_insts
        mem_alu_ratio = (load_ops + store_ops) / max(1, alu_ops)
        
        cond_density = br_cond / max(1, bb_count)
        uncond_ratio = br_uncond / max(1, br_cond + br_uncond)
        call_density = call_ops / total_insts
        fp_ratio = fp_ops / total_insts
        
        # Loop approximation from backward branches
        loop_count = max(1, int(br_cond * 0.4))
        max_depth = min(4, max(1, int(np.log2(loop_count + 1))))
        avg_bb_loop = bb_count / max(1, loop_count)
        ind_density = phi_ops / max(1, loop_count)
        
        cyclomatic = bb_count - func_count + 2 * br_cond
        spill_vuln = min(1.0, (load_ops + store_ops + phi_ops * 2) / max(1, total_insts * 0.6))
        parallel_idx = max(0.0, 1.0 - (store_ops * 1.5 + call_ops * 2.0) / max(1, total_insts))
        
        features = np.array([
            total_insts, bb_count, max(1, func_count), avg_bb_size,
            alu_ratio, logical_ratio, memory_ratio, branch_ratio, phi_ratio, vector_ratio,
            ls_ratio, alloca_ops, gep_density, mem_alu_ratio,
            cond_density, uncond_ratio, call_density, fp_ratio,
            loop_count, max_depth, avg_bb_loop, ind_density,
            cyclomatic, spill_vuln, parallel_idx
        ], dtype=np.float32)
        
        return self.normalize_features(features)

    def normalize_features(self, raw_features: np.ndarray) -> np.ndarray:
        """Normalize raw feature magnitudes to roughly [0, 1] range for neural input."""
        norm = np.copy(raw_features)
        # Scale unbounded counts via log1p or linear scaling
        norm[0] = np.log1p(norm[0]) / 8.0  # total instructions
        norm[1] = np.log1p(norm[1]) / 6.0  # basic blocks
        norm[2] = np.log1p(norm[2]) / 3.0  # functions
        norm[3] = norm[3] / 50.0           # avg bb size
        norm[11] = np.log1p(norm[11]) / 4.0 # alloca
        norm[18] = np.log1p(norm[18]) / 4.0 # loops
        norm[19] = norm[19] / 5.0          # max depth
        norm[20] = norm[20] / 20.0         # avg bb per loop
        norm[22] = np.log1p(norm[22]) / 6.0 # cyclomatic complexity
        return np.clip(norm, 0.0, 2.0)


def get_benchmark_profile(program_name: str) -> Dict[str, Union[str, np.ndarray, float]]:
    """
    Returns ground-truth synthetic/canonical profiles representing typical C/C++ benchmark programs
    under baseline -O0 compilation.
    """
    extractor = IRFeatureExtractor()
    profiles = {
        "matrix_multiply": {
            "name": "Dense Matrix Multiplication (GEMM)",
            "domain": "Linear Algebra / Numerical Computing",
            "raw_stats": [1250, 48, 2, 26.0, 0.38, 0.05, 0.32, 0.12, 0.04, 0.0, 1.4, 8, 0.18, 0.84, 0.6, 0.3, 0.01, 0.35, 6, 3, 8.0, 0.5, 32, 0.45, 0.88],
            "base_cycles": 185000.0,
            "base_code_size_kb": 124.0,
            "optimal_passes": ["LoopUnrollPass", "LoopVectorizePass", "LICMPass", "SROAPass", "GVNPass", "InstCombinePass"]
        },
        "linked_list_traversal": {
            "name": "Linked List Pointer Chasing",
            "domain": "Control Flow / Irregular Data Structures",
            "raw_stats": [680, 85, 5, 8.0, 0.15, 0.08, 0.48, 0.22, 0.08, 0.0, 2.8, 12, 0.25, 3.2, 1.4, 0.4, 0.08, 0.0, 4, 1, 21.0, 0.2, 58, 0.82, 0.12],
            "base_cycles": 94000.0,
            "base_code_size_kb": 86.0,
            "optimal_passes": ["SROAPass", "GVNPass", "SimplifyCFGPass", "MemCpyOptPass", "DeadCodeEliminationPass"]
        },
        "stencil_2d": {
            "name": "2D Jacobi Stencil Kernel",
            "domain": "PDE Solvers / Scientific Grid Computation",
            "raw_stats": [2100, 64, 3, 32.8, 0.42, 0.04, 0.36, 0.10, 0.05, 0.0, 1.2, 6, 0.22, 0.85, 0.5, 0.25, 0.01, 0.40, 8, 3, 8.0, 0.6, 42, 0.55, 0.92],
            "base_cycles": 310000.0,
            "base_code_size_kb": 158.0,
            "optimal_passes": ["LoopVectorizePass", "LICMPass", "LoopUnrollPass", "InstCombinePass", "GVNPass", "ReassociatePass"]
        },
        "quick_sort": {
            "name": "Recursive QuickSort Algorithm",
            "domain": "Sorting & Recursion / Branch Heavy",
            "raw_stats": [890, 110, 6, 8.1, 0.24, 0.12, 0.28, 0.26, 0.06, 0.0, 1.1, 14, 0.15, 1.16, 1.8, 0.35, 0.15, 0.0, 3, 1, 36.6, 0.1, 74, 0.68, 0.20],
            "base_cycles": 142000.0,
            "base_code_size_kb": 108.0,
            "optimal_passes": ["InliningPass", "TailCallEliminationPass", "SROAPass", "JumpThreadingPass", "SimplifyCFGPass"]
        },
        "fft_kernel": {
            "name": "Fast Fourier Transform (FFT 1D)",
            "domain": "Digital Signal Processing / Complex Arithmetic",
            "raw_stats": [3400, 92, 4, 36.9, 0.44, 0.06, 0.30, 0.12, 0.06, 0.0, 1.0, 10, 0.20, 0.68, 0.7, 0.3, 0.02, 0.48, 10, 3, 9.2, 0.7, 66, 0.72, 0.85],
            "base_cycles": 480000.0,
            "base_code_size_kb": 210.0,
            "optimal_passes": ["LoopVectorizePass", "LoopUnrollPass", "LICMPass", "InstCombinePass", "ReassociatePass", "GVNPass"]
        }
    }
    
    if program_name not in profiles:
        program_name = "matrix_multiply"
    
    prof = profiles[program_name]
    raw_vec = np.array(prof["raw_stats"], dtype=np.float32)
    norm_vec = extractor.normalize_features(raw_vec)
    
    return {
        "key": program_name,
        "name": prof["name"],
        "domain": prof["domain"],
        "raw_stats": raw_vec,
        "features": norm_vec,
        "base_cycles": prof["base_cycles"],
        "base_code_size_kb": prof["base_code_size_kb"],
        "optimal_passes": prof["optimal_passes"]
    }
