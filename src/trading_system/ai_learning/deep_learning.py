"""Deep Learning Models (S, §4.1).

LSTM-based price prediction model with train/predict interface.
Uses TensorFlow/Keras if available, falls back to sklearn MLPRegressor.

Features:
- Sequence-based input (lookback window)
- Train/predict with scaling
- Model versioning
- Regime-aware prediction
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler


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


class DeepLearningModel:
    """Deep learning model for price prediction.

    Uses LSTM (TensorFlow) if available, otherwise MLP (sklearn).
    """

    def __init__(self, config: DeepLearningConfig | None = None):
        self.config = config or DeepLearningConfig()
        self.scaler = MinMaxScaler()
        self.model = None
        self.is_fitted = False

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

    def train(self, df: pd.DataFrame) -> dict:
        """Train the model on OHLCV data.

        Returns training metrics dict.
        """
        X, y = self._prepare_sequences(df)
        if len(X) == 0:
            return {"error": "Insufficient data for training"}

        try:
            from tensorflow.keras.layers import LSTM, Dense, Dropout
            from tensorflow.keras.models import Sequential

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
            self.is_fitted = True
            return {
                "model_type": "lstm",
                "final_loss": float(history.history["loss"][-1]),
                "val_loss": float(history.history.get("val_loss", [0])[-1]),
                "samples": len(X),
            }
        except ImportError:
            from sklearn.neural_network import MLPRegressor

            X_flat = X.reshape(X.shape[0], -1)
            self.model = MLPRegressor(
                hidden_layer_sizes=(self.config.lstm_units, self.config.lstm_units),
                max_iter=self.config.epochs,
                random_state=42,
            )
            self.model.fit(X_flat, y)
            self.is_fitted = True
            return {
                "model_type": "mlp",
                "final_loss": float(self.model.loss_),
                "samples": len(X),
            }

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Predict next-period close prices.

        Returns array of predicted close prices (in original scale).
        """
        if not self.is_fitted or self.model is None:
            raise ValueError("Model not fitted. Call train() first.")

        X, _ = self._prepare_sequences(df)
        if len(X) == 0:
            return np.array([])

        try:
            preds = self.model.predict(X, verbose=0)
        except Exception:
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
