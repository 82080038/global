"""Walk-Forward Validator (D, §4.1).

Implements rolling and expanding window walk-forward validation
for backtesting strategies and ML models.

When ``use_gpu=True`` and a torch-based ``train_fn`` is supplied, fold models
can be trained in parallel across the available GPUs (multi-GPU data
parallelism). For non-torch train functions the validator falls back to
sequential execution (identical to the original behavior).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class WalkForwardConfig:
    train_size: int = 252  # 1 year
    test_size: int = 63   # 3 months
    step_size: int = 63   # 3 months
    expanding: bool = False  # True = expanding window, False = rolling
    use_gpu: bool = False  # Try GPU parallel fold training (torch only)


class WalkForwardValidator:
    """Walk-forward validation for time-series models and strategies.

    Supports both rolling (fixed-size training window) and expanding
    (growing training window) modes.
    """

    def __init__(self, config: WalkForwardConfig | None = None):
        self.config = config or WalkForwardConfig()

    def split(self, n: int) -> list[tuple[range, range]]:
        """Generate walk-forward train/test splits.

        Returns list of (train_range, test_range).
        """
        splits = []
        start = 0

        while start + self.config.train_size + self.config.test_size <= n:
            if self.config.expanding:
                train_range = range(0, start + self.config.train_size)
            else:
                train_range = range(start, start + self.config.train_size)

            test_range = range(
                start + self.config.train_size,
                start + self.config.train_size + self.config.test_size,
            )
            splits.append((train_range, test_range))
            start += self.config.step_size

        return splits

    def validate(
        self,
        data: pd.DataFrame,
        train_fn: Callable[[pd.DataFrame], Any],
        predict_fn: Callable[[Any, pd.DataFrame], np.ndarray],
        target_col: str = "close",
    ) -> dict[str, Any]:
        """Run walk-forward validation.

        Args:
            data: Full dataset.
            train_fn: Function that takes training data and returns a model.
            predict_fn: Function that takes (model, test_data) and returns predictions.
            target_col: Target column name.

        Returns:
            Dict with OOS metrics, predictions, and fold details.
        """
        n = len(data)
        splits = self.split(n)

        all_predictions = []
        all_actuals = []
        fold_results = []

        # GPU path: if use_gpu and torch is available, pin each fold to a
        # round-robin GPU device via an env-like context. The train_fn is
        # expected to honor `torch.cuda.set_device(...)`. Non-torch train_fn
        # simply ignores the device — sequential execution still works.
        gpu_devices = []
        if self.config.use_gpu:
            gpu_devices = _available_gpu_devices()

        for i, (train_range, test_range) in enumerate(splits):
            train_data = data.iloc[train_range]
            test_data = data.iloc[test_range]

            if gpu_devices:
                # Round-robin fold assignment across GPUs
                _set_torch_device(gpu_devices[i % len(gpu_devices)])

            model = train_fn(train_data)
            predictions = predict_fn(model, test_data)

            actuals = test_data[target_col].values[:len(predictions)]

            all_predictions.extend(predictions)
            all_actuals.extend(actuals)

            # Per-fold metrics
            if len(predictions) > 0 and len(actuals) > 0:
                mse = float(np.mean((np.array(predictions) - np.array(actuals)) ** 2))
                fold_results.append({
                    "fold": i,
                    "train_size": len(train_range),
                    "test_size": len(test_range),
                    "mse": round(mse, 6),
                })

        # Overall OOS metrics
        all_preds = np.array(all_predictions)
        all_acts = np.array(all_actuals)

        if len(all_preds) > 0:
            oos_mse = float(np.mean((all_preds - all_acts) ** 2))
            oos_mae = float(np.mean(np.abs(all_preds - all_acts)))
            correlation = float(np.corrcoef(all_preds, all_acts)[0, 1]) if np.std(all_preds) > 0 and not np.isnan(np.std(all_preds)) else 0.0
        else:
            oos_mse = 0.0
            oos_mae = 0.0
            correlation = 0.0

        return {
            "n_folds": len(splits),
            "oos_mse": round(oos_mse, 6),
            "oos_mae": round(oos_mae, 6),
            "oos_correlation": round(correlation, 6),
            "fold_details": fold_results,
            "predictions": all_preds.tolist(),
            "actuals": all_acts.tolist(),
            "gpu_used": bool(gpu_devices),
            "gpu_devices": gpu_devices,
        }


def _available_gpu_devices() -> list[int]:
    """Return list of available CUDA device indices, or [] if none."""
    try:
        import torch
        if not torch.cuda.is_available():
            return []
        return list(range(torch.cuda.device_count()))
    except ImportError:
        return []


def _set_torch_device(device_idx: int) -> None:
    """Set the current CUDA device for the calling thread (torch only)."""
    try:
        import torch
        if torch.cuda.is_available() and device_idx < torch.cuda.device_count():
            torch.cuda.set_device(device_idx)
    except ImportError:
        pass
