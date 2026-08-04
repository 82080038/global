# GPU / CUDA ML Workflow

Use this skill when working on machine learning tasks that can benefit from GPU
acceleration (training, inference, batch prediction, hyperparameter search) in
`src/trading_system/ai_learning/` or related modules.

## Hardware

- 2x NVIDIA GeForce GTX 1050 Ti (Pascal, compute capability 6.1, 4 GB VRAM each)
- GPU 0 is shared with the display server (Xorg/GNOME) — **prefer `cuda:1`** for compute
- GPU 1 is free for ML workloads
- No Tensor Cores → FP32 is the main path; FP16 gains are minimal

## Quick checks

```bash
# GPU status + VRAM usage
nvidia-smi

# PyTorch CUDA availability + device pick
.venv/bin/python -c "import torch; print(torch.cuda.is_available(), torch.cuda.device_count())"
```

## PyTorch device selection

Use the helper in `ai_learning/deep_learning.py`:

```python
from trading_system.ai_learning.deep_learning import _pick_torch_device
device = _pick_torch_device("auto")  # -> "cuda:1" if available, else "cuda:0", else "cpu"
```

Or directly:

```python
import torch
device = torch.device("cuda:1" if torch.cuda.device_count() >= 2 else
                      "cuda:0" if torch.cuda.is_available() else "cpu")
x = x.to(device)
```

## VRAM budget (4 GB per GPU)

| Model | Hidden | Batch | VRAM (approx) | OK? |
|-------|--------|-------|----------------|-----|
| LSTM (2-layer) | 50 | 32 | ~300 MB | Yes |
| LSTM (2-layer) | 128 | 64 | ~800 MB | Yes |
| LSTM (2-layer) | 256 | 128 | ~1.8 GB | Borderline |
| Small Transformer | 256 | 64 | ~2.5 GB | Tight |
| ResNet-18 (vision) | - | 32 | ~1.5 GB | Yes |

Rules of thumb:
- Keep `batch_size <= 64` and `hidden_dim <= 256` for safety
- Call `torch.cuda.empty_cache()` between unrelated workloads
- Use `with torch.no_grad():` for inference to save autograd memory
- For walk-forward / grid search, run folds sequentially (NCCL multi-GPU is
  not useful here — no NVLink, and 4 GB/GPU is too small to shard)

## Backend fallback chain

`DeepLearningModel` (in `ai_learning/deep_learning.py`) auto-selects:

1. **PyTorch** (CUDA) — primary, uses `cuda:1` by default
2. **TensorFlow/Keras** — secondary (if torch missing)
3. **sklearn MLPRegressor** — final fallback (CPU only)

Override via `DeepLearningConfig(backend="torch"|"tensorflow"|"sklearn")`.

## Install / reinstall

```bash
# From repo root
.venv/bin/python -m pip install -e ".[gpu]" --index-url https://download.pytorch.org/whl/cu121
```

## When NOT to use GPU

- Datasets < ~5000 rows → CPU is faster (PCIe transfer overhead dominates)
- Monte Carlo with `n_simulations < 2000` → CPU wins (CUDA init ~1s overhead)
- sklearn-only models (RandomForest, LR, XGBoost) — no CUDA path
- pandas/numpy operations — already CPU-optimized
- Devin's own reasoning — runs on Cognition servers, not local GPU

## CUDA-injected modules (auto-active)

| Module | GPU path | Trigger | Speedup |
|--------|----------|---------|---------|
| `ai_learning/deep_learning.py` | PyTorch LSTM on `cuda:1` | `backend="auto"` (default) | 2-5x training |
| `backtest/metrics.py` | Vectorized MC on `cuda:1` | `use_gpu=True` + `n_simulations >= 2000` | **51x** at 5000 sims |
| `ai_learning/walk_forward.py` | Round-robin fold→GPU | `WalkForwardConfig(use_gpu=True)` | multi-GPU parallel |

API endpoints that auto-use GPU:
- `POST /api/backtest/monte-carlo` — vectorized MC (returns `"backend":"gpu"`)
- `POST /api/ai/train` — LSTM training via `DeepLearningModel`
- `POST /api/backtest/walk-forward` — set `use_gpu=true` in payload

## Common pitfalls

- **CUDA OOM**: reduce batch_size or hidden_dim; call `torch.cuda.empty_cache()`
- **Slow first run**: CUDA context init takes ~2-3s on first kernel launch
- **GPU 0 contention**: Xorg + GNOME use ~300 MB VRAM on GPU 0; use `cuda:1`
- **Driver vs toolkit mismatch**: driver supports CUDA 13.0, torch built with 12.1 — fine (forward compatible)
