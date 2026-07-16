"""
Shared Neural Program Encoder
Transforms 25-dimensional normalized LLVM IR feature vectors into a shared d=512 latent embedding vector.
Supports pure Numpy inference (for instant self-contained evaluation) and PyTorch nn.Module (when PyTorch is installed).
"""

import numpy as np
from typing import Union

# Try importing PyTorch if available
try:
    import torch
    import torch.nn as nn
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

class SharedProgramEncoder:
    """
    3-Layer Residual Multi-Layer Perceptron (MLP) mapping 25-D statistics to d=512 latent space.
    Architecture:
      Input (25) -> Linear(25, 128) -> SiLU -> Linear(128, 256) -> SiLU -> Linear(256, 512) + Residual projection
    """
    def __init__(self, input_dim: int = 25, latent_dim: int = 512, seed: int = 42):
        self.input_dim = input_dim
        self.latent_dim = latent_dim
        self.rng = np.random.RandomState(seed)
        
        # Initialize orthogonal weights for deterministic forward passes
        self.W1 = self._orthogonal_init(input_dim, 128)
        self.b1 = np.zeros(128, dtype=np.float32)
        
        self.W2 = self._orthogonal_init(128, 256)
        self.b2 = np.zeros(256, dtype=np.float32)
        
        self.W3 = self._orthogonal_init(256, latent_dim)
        self.b3 = np.zeros(latent_dim, dtype=np.float32)
        
        # Residual skip projection
        self.W_skip = self._orthogonal_init(input_dim, latent_dim)

    def _orthogonal_init(self, rows: int, cols: int) -> np.ndarray:
        """He/Orthogonal initialization for stable numerical scaling."""
        a = self.rng.normal(0.0, 1.0, (rows, cols)).astype(np.float32)
        if rows < cols:
            return a * np.sqrt(2.0 / rows)
        u, _, v = np.linalg.svd(a, full_matrices=False)
        q = u if u.shape == (rows, cols) else v
        return (q * np.sqrt(2.0 / max(1, rows))).astype(np.float32)

    def _silu(self, x: np.ndarray) -> np.ndarray:
        """SiLU / Swish activation: x * sigmoid(x)"""
        return x / (1.0 + np.exp(-np.clip(x, -15.0, 15.0)))

    def encode(self, features: np.ndarray) -> np.ndarray:
        """
        Compute d=512 latent program embedding z from 25-D features.
        Accepts 1D vector (25,) or 2D batch (B, 25).
        """
        x = np.atleast_2d(features.astype(np.float32))
        
        h1 = self._silu(np.dot(x, self.W1) + self.b1)
        h2 = self._silu(np.dot(h1, self.W2) + self.b2)
        h3 = np.dot(h2, self.W3) + self.b3
        
        skip = np.dot(x, self.W_skip)
        
        z = self._silu(h3 + skip)
        
        # L2 normalize embedding vector
        norms = np.linalg.norm(z, axis=-1, keepdims=True)
        z_norm = z / np.maximum(norms, 1e-6)
        
        return z_norm[0] if features.ndim == 1 else z_norm


if HAS_TORCH:
    class PyTorchSharedEncoder(nn.Module):
        """PyTorch nn.Module implementation of the Shared Program Encoder for GPU training."""
        def __init__(self, input_dim: int = 25, latent_dim: int = 512):
            super().__init__()
            self.fc1 = nn.Linear(input_dim, 128)
            self.act1 = nn.SiLU()
            self.fc2 = nn.Linear(128, 256)
            self.act2 = nn.SiLU()
            self.fc3 = nn.Linear(256, latent_dim)
            self.skip = nn.Linear(input_dim, latent_dim)
            self.act_out = nn.SiLU()

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            h1 = self.act1(self.fc1(x))
            h2 = self.act2(self.fc2(h1))
            h3 = self.fc3(h2) + self.skip(x)
            z = self.act_out(h3)
            return torch.nn.functional.normalize(z, p=2, dim=-1)
