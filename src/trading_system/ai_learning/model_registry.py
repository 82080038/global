"""Model Registry (L, §4.1).

Tracks model versions, metadata, and performance metrics.
Stores model artifacts in a local directory structure.

Features:
- Register model with version and metadata
- Load model by name/version
- Compare model versions
- Track performance metrics over time
- Promote/demote model status (experiment/staging/production)
"""

from __future__ import annotations

import json
import pickle
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class ModelRecord:
    name: str
    version: str
    status: str = "experiment"  # experiment, staging, production
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metrics: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    artifact_path: str = ""


class ModelRegistry:
    """Registry for tracking and managing ML model versions.

    Stores models in a directory structure:
        {registry_dir}/{model_name}/{version}/model.pkl
        {registry_dir}/{model_name}/{version}/metadata.json
    """

    def __init__(self, registry_dir: str | Path | None = None):
        if registry_dir is None:
            registry_dir = Path(__file__).parent / "model_store"
        self.registry_dir = Path(registry_dir)
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, dict[str, ModelRecord]] = {}
        self._load_index()

    def _load_index(self) -> None:
        """Load index from disk."""
        index_file = self.registry_dir / "index.json"
        if index_file.exists():
            with open(index_file) as f:
                data = json.load(f)
            for name, versions in data.items():
                self._index[name] = {
                    v: ModelRecord(**record) for v, record in versions.items()
                }

    def _save_index(self) -> None:
        """Save index to disk."""
        index_file = self.registry_dir / "index.json"
        data = {}
        for name, versions in self._index.items():
            data[name] = {v: asdict(r) for v, r in versions.items()}
        with open(index_file, "w") as f:
            json.dump(data, f, indent=2)

    def register(
        self,
        name: str,
        version: str,
        model: Any,
        metrics: dict[str, float] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ModelRecord:
        """Register a new model version.

        Args:
            name: Model name.
            version: Version string (e.g., "1.0", "1.1").
            model: Model object (picklable).
            metrics: Performance metrics dict.
            metadata: Additional metadata.

        Returns:
            ModelRecord for the registered model.
        """
        model_dir = self.registry_dir / name / version
        model_dir.mkdir(parents=True, exist_ok=True)

        artifact_path = model_dir / "model.pkl"
        with open(artifact_path, "wb") as f:
            pickle.dump(model, f)

        record = ModelRecord(
            name=name,
            version=version,
            metrics=metrics or {},
            metadata=metadata or {},
            artifact_path=str(artifact_path),
        )

        if name not in self._index:
            self._index[name] = {}
        self._index[name][version] = record
        self._save_index()

        return record

    def load(self, name: str, version: str | None = None) -> Any:
        """Load a model by name and version.

        If version is None, loads the production version.
        """
        if name not in self._index:
            raise KeyError(f"Model '{name}' not found in registry")

        if version is None:
            version = self._get_production_version(name)

        if version not in self._index[name]:
            raise KeyError(f"Version '{version}' not found for model '{name}'")

        record = self._index[name][version]
        with open(record.artifact_path, "rb") as f:
            return pickle.load(f)

    def _get_production_version(self, name: str) -> str:
        """Get the production version for a model."""
        for version, record in self._index[name].items():
            if record.status == "production":
                return version
        # Fallback to latest version
        return sorted(self._index[name].keys())[-1]

    def promote(self, name: str, version: str, status: str = "production") -> None:
        """Promote a model version to a new status."""
        if name not in self._index or version not in self._index[name]:
            raise KeyError(f"Model '{name}' version '{version}' not found")

        if status == "production":
            # Demote other production versions
            for v, r in self._index[name].items():
                if r.status == "production":
                    r.status = "staging"

        self._index[name][version].status = status
        self._save_index()

    def list_versions(self, name: str) -> list[ModelRecord]:
        """List all versions of a model."""
        if name not in self._index:
            return []
        return list(self._index[name].values())

    def compare(
        self, name: str, version_a: str, version_b: str
    ) -> dict[str, dict[str, float]]:
        """Compare metrics between two model versions."""
        if name not in self._index:
            raise KeyError(f"Model '{name}' not found")

        ra = self._index[name].get(version_a)
        rb = self._index[name].get(version_b)
        if ra is None or rb is None:
            raise KeyError("Version not found")

        return {
            version_a: ra.metrics,
            version_b: rb.metrics,
        }

    def get_best_version(self, name: str, metric: str = "sharpe") -> str | None:
        """Get the version with the best value for a given metric."""
        if name not in self._index or not self._index[name]:
            return None
        best_version = None
        best_value = float("-inf")
        for version, record in self._index[name].items():
            value = record.metrics.get(metric, float("-inf"))
            if value > best_value:
                best_value = value
                best_version = version
        return best_version
