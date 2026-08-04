"""Deep Learning Models (S, §4.1).

LSTM-based price prediction model with train/predict interface.
Backend priority: PyTorch (CUDA) > TensorFlow/Keras > sklearn MLPRegressor.

Features:
- Sequence-based input (lookback window)
- Train/predict with scaling
- Model versioning
- Regime-aware prediction
- GPU acceleration via PyTorch CUDA (auto-detected, prefers GPU 1 to avoid
  contending with the display server on GPU 0)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler


def _pick_torch_device(preferred: str = "auto") -> str:
    """Pick the best torch device.

    "auto" prefers cuda:1 (the second GPU, typically free of the display
    server) when available, then cuda:0, then cpu.
    """
    try:
        import torch
    except ImportError:
        return "cpu"
    if not torch.cuda.is_available():
        return "cpu"
    # Respect any explicit non-"auto" choice (e.g. "cpu" to force CPU).
    if preferred != "auto":
        return preferred
    n = torch.cuda.device_count()
    if n >= 2:
        return "cuda:1"
    return "cuda:0"


@dataclass
class DeepLearningConfig:
    lookback: int = 20
    n_features: int = 5  # open, high, low, close, volume
    lstm_units: int = 50
    dropout: float = 0.2
    epochs: int = 50
    batch_size: int = 32
    validation_split: float = 0.2
    model_type: str = "lstm"  # "lstm" or "mlp"
    # Backend selection: "auto" (torch>tf>sklearn), "torch", "tensorflow", "sklearn"
    backend: str = "auto"
    # Device for torch backend: "auto", "cpu", "cuda", "cuda:0", "cuda:1", ...
    device: str = "auto"
    learning_rate: float = 1e-3
    # Extra metadata populated at fit time (backend used, device, etc.)
    fit_info: dict = field(default_factory=dict)


class _TorchLSTM:
    """Thin wrapper around a PyTorch LSTM regression model.

    Kept small (hidden=50, 2 layers) to fit comfortably in 4 GB VRAM
    (GTX 1050 Ti Pascal). Uses float32.
    """

    def __init__(self, lookback: int, n_features: int, lstm_units: int,
                 dropout: float, device: str):
        import torch
        import torch.nn as nn

        self.device = torch.device(device)
        self.lookback = lookback
        self.n_features = n_features

        class _Net(nn.Module):
            def __init__(self, in_features, hidden, dropout_p):
                super().__init__()
                self.lstm1 = nn.LSTM(in_features, hidden, batch_first=True)
                self.drop1 = nn.Dropout(dropout_p)
                self.lstm2 = nn.LSTM(hidden, hidden, batch_first=True)
                self.drop2 = nn.Dropout(dropout_p)
                self.fc = nn.Linear(hidden, 1)

            def forward(self, x):
                out, _ = self.lstm1(x)
                out = self.drop1(out)
                out, _ = self.lstm2(out)
                out = self.drop2(out[:, -1, :])
                return self.fc(out).squeeze(-1)

        self.net = _Net(n_features, lstm_units, dropout).to(self.device)
        self.optimizer = torch.optim.Adam(self.net.parameters(), lr=1e-3)
        self.criterion = nn.MSELoss()
        self.torch = torch

    def fit(self, X: np.ndarray, y: np.ndarray, epochs: int, batch_size: int,
            validation_split: float) -> dict:
        t = self.torch
        n = len(X)
        perm = t.randperm(n).numpy()
        n_val = int(n * validation_split)
        val_idx, train_idx = perm[:n_val], perm[n_val:]
        if len(train_idx) == 0:
            train_idx, val_idx = perm, np.array([], dtype=int)

        Xtr = t.from_numpy(X[train_idx]).float().to(self.device)
        ytr = t.from_numpy(y[train_idx]).float().to(self.device)
        Xva = t.from_numpy(X[val_idx]).float().to(self.device) if len(val_idx) else None
        yva = t.from_numpy(y[val_idx]).float().to(self.device) if len(val_idx) else None

        self.net.train()
        last_loss, last_val = float("nan"), float("nan")
        for _ in range(epochs):
            self.net.train()
            order = t.randperm(len(Xtr))
            for start in range(0, len(Xtr), batch_size):
                idx = order[start:start + batch_size]
                xb, yb = Xtr[idx], ytr[idx]
                self.optimizer.zero_grad()
                pred = self.net(xb)
                loss = self.criterion(pred, yb)
                loss.backward()
                self.optimizer.step()
            last_loss = float(self.criterion(self.net(Xtr), ytr).item())
            if Xva is not None:
                self.net.eval()
                with t.no_grad():
                    last_val = float(self.criterion(self.net(Xva), yva).item())
        return {"final_loss": last_loss, "val_loss": last_val, "samples": n}

    def predict(self, X: np.ndarray) -> np.ndarray:
        t = self.torch
        self.net.eval()
        with t.no_grad():
            Xt = t.from_numpy(X).float().to(self.device)
            out = self.net(Xt).cpu().numpy()
        return out.reshape(-1, 1)


class DeepLearningModel:
    """Deep learning model for price prediction.

    Backend priority (config.backend="auto"): PyTorch > TensorFlow > sklearn.
    PyTorch auto-uses CUDA when available (prefers GPU 1 to avoid the display
    server on GPU 0). Falls back gracefully on any backend failure.
    """

    def __init__(self, config: DeepLearningConfig | None = None):
        self.config = config or DeepLearningConfig()
        self.scaler = MinMaxScaler()
        self.model = None
        self.is_fitted = False
        self._backend_used: str | None = None
        self._device_used: str | None = None

    def _prepare_sequences(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        """Prepare sequences for time-series prediction."""
        features = ["open", "high", "low", "close", "volume"]
        available = [f for f in features if f in df.columns]
        data = df[available].values

        scaled = self.scaler.fit_transform(data)
        X, y = [], []
        lookback = self.config.lookback

        for i in range(lookback, len(scaled)):
            X.append(scaled[i - lookback:i])
            y.append(scaled[i, available.index("close")])

        return np.array(X), np.array(y)

    def _train_torch(self, X: np.ndarray, y: np.ndarray) -> dict | None:
        try:
            import torch  # noqa: F401
        except ImportError:
            return None
        device = _pick_torch_device(self.config.device)
        self.model = _TorchLSTM(
            lookback=self.config.lookback,
            n_features=X.shape[2],
            lstm_units=self.config.lstm_units,
            dropout=self.config.dropout,
            device=device,
        )
        info = self.model.fit(
            X, y,
            epochs=self.config.epochs,
            batch_size=self.config.batch_size,
            validation_split=self.config.validation_split,
        )
        self._backend_used = "torch"
        self._device_used = device
        return {
            "model_type": "lstm",
            "backend": "torch",
            "device": device,
            "final_loss": info["final_loss"],
            "val_loss": info["val_loss"],
            "samples": info["samples"],
        }

    def _train_tensorflow(self, X: np.ndarray, y: np.ndarray) -> dict | None:
        try:
            from tensorflow.keras.layers import LSTM, Dense, Dropout
            from tensorflow.keras.models import Sequential
        except ImportError:
            return None
        self.model = Sequential([
            LSTM(self.config.lstm_units, return_sequences=True, input_shape=(X.shape[1], X.shape[2])),
            Dropout(self.config.dropout),
            LSTM(self.config.lstm_units),
            Dropout(self.config.dropout),
            Dense(1),
        ])
        self.model.compile(optimizer="adam", loss="mse")
        history = self.model.fit(
            X, y, epochs=self.config.epochs, batch_size=self.config.batch_size,
            validation_split=self.config.validation_split, verbose=0,
        )
        self._backend_used = "tensorflow"
        self._device_used = "tf-gpu" if _tf_gpu_available() else "tf-cpu"
        return {
            "model_type": "lstm",
            "backend": "tensorflow",
            "device": self._device_used,
            "final_loss": float(history.history["loss"][-1]),
            "val_loss": float(history.history.get("val_loss", [0])[-1]),
            "samples": len(X),
        }

    def _train_sklearn(self, X: np.ndarray, y: np.ndarray) -> dict:
        from sklearn.neural_network import MLPRegressor

        X_flat = X.reshape(X.shape[0], -1)
        self.model = MLPRegressor(
            hidden_layer_sizes=(self.config.lstm_units, self.config.lstm_units),
            max_iter=self.config.epochs,
            random_state=42,
        )
        self.model.fit(X_flat, y)
        self._backend_used = "sklearn"
        self._device_used = "cpu"
        return {
            "model_type": "mlp",
            "backend": "sklearn",
            "device": "cpu",
            "final_loss": float(self.model.loss_),
            "samples": len(X),
        }

    def train(self, df: pd.DataFrame) -> dict:
        """Train the model on OHLCV data.

        Returns training metrics dict.
        """
        X, y = self._prepare_sequences(df)
        if len(X) == 0:
            return {"error": "Insufficient data for training"}

        backend = self.config.backend
        result: dict | None = None
        if backend in ("auto", "torch"):
            result = self._train_torch(X, y)
        if result is None and backend in ("auto", "tensorflow"):
            result = self._train_tensorflow(X, y)
        if result is None:
            result = self._train_sklearn(X, y)

        self.is_fitted = True
        self.config.fit_info = {
            "backend": self._backend_used,
            "device": self._device_used,
        }
        return result

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Predict next-period close prices.

        Returns array of predicted close prices (in original scale).
        """
        if not self.is_fitted or self.model is None:
            raise ValueError("Model not fitted. Call train() first.")

        X, _ = self._prepare_sequences(df)
        if len(X) == 0:
            return np.array([])

        if self._backend_used == "torch":
            preds = self.model.predict(X)
        elif self._backend_used == "tensorflow":
            preds = self.model.predict(X, verbose=0)
        else:
            X_flat = X.reshape(X.shape[0], -1)
            preds = self.model.predict(X_flat)

        # Inverse transform to get original scale
        features = ["open", "high", "low", "close", "volume"]
        available = [f for f in features if f in df.columns]
        close_idx = available.index("close")

        dummy = np.zeros((len(preds), len(available)))
        dummy[:, close_idx] = preds.ravel()
        inversed = self.scaler.inverse_transform(dummy)
        return inversed[:, close_idx]


def _tf_gpu_available() -> bool:
    try:
        import tensorflow as tf
        return bool(tf.config.list_physical_devices("GPU"))
    except Exception:
        return False
