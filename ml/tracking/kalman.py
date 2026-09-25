"""Constant-velocity Kalman filter in a local tangent plane (km, km/h).

State x = [east, north, v_east, v_north]. Process noise is white-noise acceleration with spectral
density ``sigma_accel`` (km/h^2). Measurements are region centroids with isotropic noise ``sigma_meas`` (km).
"""
from __future__ import annotations

import numpy as np

CHI2_95_2DOF = 5.991  # 95 % quantile of chi-square with 2 degrees of freedom


class ConstantVelocityKalman:
    """2-D constant-velocity Kalman filter with variable time step."""

    def __init__(self, x: float, y: float, sigma_meas: float, sigma_accel: float, sigma_v0: float) -> None:
        self.sigma_meas = sigma_meas
        self.sigma_accel = sigma_accel
        self.x = np.array([x, y, 0.0, 0.0])
        self.P = np.diag([sigma_meas**2, sigma_meas**2, sigma_v0**2, sigma_v0**2])

    def _matrices(self, dt: float) -> tuple[np.ndarray, np.ndarray]:
        f = np.eye(4)
        f[0, 2] = f[1, 3] = dt
        q = self.sigma_accel**2
        blk = np.array([[dt**3 / 3.0, dt**2 / 2.0], [dt**2 / 2.0, dt]]) * q
        qm = np.zeros((4, 4))
        qm[np.ix_([0, 2], [0, 2])] = blk
        qm[np.ix_([1, 3], [1, 3])] = blk
        return f, qm

    def predicted(self, dt: float) -> tuple[np.ndarray, np.ndarray]:
        """State and covariance after ``dt`` hours, without changing the filter."""
        f, q = self._matrices(dt)
        return f @ self.x, f @ self.P @ f.T + q

    def predict(self, dt: float) -> None:
        self.x, self.P = self.predicted(dt)

    def update(self, zx: float, zy: float) -> None:
        h = np.zeros((2, 4))
        h[0, 0] = h[1, 1] = 1.0
        r = np.eye(2) * self.sigma_meas**2
        s = h @ self.P @ h.T + r
        k = self.P @ h.T @ np.linalg.inv(s)
        self.x = self.x + k @ (np.array([zx, zy]) - h @ self.x)
        self.P = (np.eye(4) - k @ h) @ self.P

    def position_radius_km(self, cov: np.ndarray | None = None) -> float:
        """Radius of the 95 % position confidence circle (uses the larger eigenvalue)."""
        p = (self.P if cov is None else cov)[:2, :2]
        return float(np.sqrt(CHI2_95_2DOF * np.linalg.eigvalsh(p).max()))
