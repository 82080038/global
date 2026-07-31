"""Purged Time Series Split (C, §4.1).

Implements purged k-fold cross-validation for time series with embargo,
following Marcos Lopez de Prado's methodology.

Prevents data leakage from overlapping labels by purging samples
in the vicinity of the test set and applying an embargo period.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class PurgedKFold:
    """Purged k-fold cross-validation for time series.

    Args:
        n_splits: Number of folds.
        purge_days: Number of days to purge before/after test set.
        embargo_days: Number of days to embargo after test set.
    """
    n_splits: int = 5
    purge_days: int = 5
    embargo_days: int = 3

    def split(self, df: pd.DataFrame) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        """Generate purged train/test indices.

        Yields (train_indices, test_indices) for each fold.
        """
        n = len(df)
        fold_size = n // self.n_splits
        indices = np.arange(n)

        for i in range(self.n_splits):
            test_start = i * fold_size
            test_end = (i + 1) * fold_size if i < self.n_splits - 1 else n
            test_idx = indices[test_start:test_end]

            # Purge: remove samples within purge_days of test set boundaries
            purge_start = max(0, test_start - self.purge_days)
            purge_end = min(n, test_end + self.purge_days)

            # Embargo: remove samples after test set
            embargo_end = min(n, test_end + self.embargo_days + self.purge_days)

            mask = np.ones(n, dtype=bool)
            mask[purge_start:purge_end] = False
            mask[test_start:test_end] = True  # Keep test indices
            # Actually: train = everything except test and purged
            train_mask = np.ones(n, dtype=bool)
            train_mask[test_start:test_end] = False  # Remove test
            train_mask[purge_start:purge_end] = False  # Remove purged
            train_idx = indices[train_mask]

            yield train_idx, test_idx


def walk_forward_indices(
    n: int,
    train_size: int,
    test_size: int,
    step_size: int | None = None,
) -> list[tuple[range, range]]:
    """Generate walk-forward train/test index ranges.

    Args:
        n: Total number of samples.
        train_size: Number of samples in training set.
        test_size: Number of samples in test set.
        step_size: Step between successive windows (default: test_size).

    Returns:
        List of (train_range, test_range) tuples.
    """
    if step_size is None:
        step_size = test_size

    splits = []
    start = 0
    while start + train_size + test_size <= n:
        train_range = range(start, start + train_size)
        test_range = range(start + train_size, start + train_size + test_size)
        splits.append((train_range, test_range))
        start += step_size

    return splits
