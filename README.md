#NeuroCompiler: A Hybrid ML + RL Guided Optimization Framework for LLVM

Project Summary

NeuroCompiler is a machine learning–augmented compiler optimization framework built on top of the LLVM infrastructure. The system introduces a hybrid Supervised Learning and Reinforcement Learning decision layer into the compiler pipeline to improve optimization decisions beyond traditional heuristic-based approaches.

The framework learns program representations from LLVM Intermediate Representation (IR) using neural encoders (e.g., Graph Neural Networks or Transformer-based models). These embeddings are used to:

Predict optimization pass profitability
Assist register allocation decisions (spill risk prediction)
Guide vectorization and parallelization decisions
Dynamically select and order optimization passes using a Reinforcement Learning agent

Unlike static optimization levels (-O2, -O3), NeuroCompiler adapts its optimization strategy per program, aiming to improve runtime performance while controlling compilation overhead.

The project evaluates the hybrid system against standard LLVM optimization pipelines using benchmark programs and measures:

Execution time improvements
Code size impact
Compilation time overhead
Generalization across unseen programs

The primary research objective is to determine whether a hybrid ML + RL approach can outperform static compiler heuristics in optimization decision-making.
