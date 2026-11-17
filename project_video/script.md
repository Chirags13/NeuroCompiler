# NeuroCompiler explainer: narration script

Voice: `en-US-AndrewNeural` (Microsoft neural voice via edge-tts). Length 1:42. Lines are as captioned; the voice reads numbers and acronyms spelled out (see `narration.py`).

## 0:00 Introduction

Compile with -O3,  
and 109 passes run  
in the same order, for every program.  
NeuroCompiler looks for a faster recipe per program,  
and proves it with a stopwatch.  

## 0:11 Problem

That recipe is a compromise.  
One edit speeds some programs up and slows others down.  
And the easy metric is a trap:  
across 18,000 timed candidates,  
IR instruction count barely predicted speed.  

## 0:23 Measurement

So, one rule: only measured runtime counts.  
Candidates race -O3 in shuffled rounds on a pinned core,  
beside an identical copy that exposes noise.  
If the output changes, the candidate is rejected.  

## 0:37 Data and models

We searched 146 real programs,  
building over 70,000 candidates.  
That data trains two models.  
LightGBM predicts a pipeline's speedup.  
PPO, a reinforcement learning agent, invents new ones, edit by edit.  

## 0:52 How tune mode works

For a new program, PPO proposes 24 pipelines.  
LightGBM ranks them with about 900 more.  
The top 8 are compiled, verified and timed.  
The fastest must win again in a fresh run,  
or -O3 ships.  
The models shortlist. The stopwatch decides.  

## 1:09 Results

On 33 programs from unseen families,  
it averages 8% faster than -O3,  
about 5% without its biggest win,  
and none got measurably slower.  
On one interpreter demo, runtime fell from 850 ms to 220.  

## 1:24 Implementation and honest lesson

Built on LLVM 18,  
with a live dashboard showing every changed pass.  
The lesson: alone, the models are weak, and RL added little.  
Measurement makes it reliable.  

## 1:36 Close

NeuroCompiler. Faster code, measured, not guessed.  
