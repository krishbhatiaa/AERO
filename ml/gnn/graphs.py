"""Graph construction for spatio-temporal GNNs (NumPy/SciPy only; no deep-learning dependency).

The graph abstraction is deliberately independent of any model so meshes can evolve without touching
model code. All geometry is on the sphere (3-D unit vectors); chord distances are converted to great-circle
km. Builders return :class:`Graph` objects with directed edges in both directions.

* :func:`knn_graph`         k nearest neighbours (chord distance)
* :func:`radius_graph`      all pairs within ``radius_km``
* :func:`latlon_grid_graph` 8-neighbour grid mesh (periodic in longitude for global grids)
* :func:`icosahedral_mesh`  recursively subdivided icosahedron: V = 10*4^L + 2, E = 30*4^L (undirected)
* :func:`grid_to_mesh_edges` bipartite k-NN edges (grid encoder / decoder wiring, GraphCast-style)

Edge attributes: ``[distance_km, dx_km, dy_km]`` with (dx, dy) the displacement in the sender's local
east/north tangent frame.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from ml.core.geometry import EARTH_RADIUS_KM
from ml.core.grid import GridSpec


@dataclass(frozen=True)
class Graph:
    """Directed graph on the sphere."""

    xyz: np.ndarray  # (N, 3) unit vectors
    latlon: np.ndarray  # (N, 2) degrees
    edge_index: np.ndarray  # (2, E) [sender; receiver]
    edge_attr: np.ndarray  # (E, 3) [distance_km, dx_km, dy_km]

    @property
    def n_nodes(self) -> int:
        return int(self.xyz.shape[0])

    @property
    def n_edges(self) -> int:
        return int(self.edge_index.shape[1])


def latlon_to_xyz(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    phi, lam = np.radians(lat), np.radians(lon)
    return np.stack([np.cos(phi) * np.cos(lam), np.cos(phi) * np.sin(lam), np.sin(phi)], axis=-1)


def xyz_to_latlon(xyz: np.ndarray) -> np.ndarray:
    return np.stack([np.degrees(np.arcsin(np.clip(xyz[:, 2], -1, 1))), np.degrees(np.arctan2(xyz[:, 1], xyz[:, 0]))], axis=-1)


def _edge_attr(xyz_s: np.ndarray, xyz_r: np.ndarray, ei: np.ndarray, sender_latlon: np.ndarray) -> np.ndarray:
    s, r = xyz_s[ei[0]], xyz_r[ei[1]]
    chord = np.linalg.norm(r - s, axis=1)
    dist = 2.0 * EARTH_RADIUS_KM * np.arcsin(np.clip(chord / 2.0, 0, 1))
    phi, lam = np.radians(sender_latlon[ei[0], 0]), np.radians(sender_latlon[ei[0], 1])
    east = np.stack([-np.sin(lam), np.cos(lam), np.zeros_like(lam)], axis=1)
    north = np.stack([-np.sin(phi) * np.cos(lam), -np.sin(phi) * np.sin(lam), np.cos(phi)], axis=1)
    d = (r - s) * EARTH_RADIUS_KM
    return np.stack([dist, np.einsum("ij,ij->i", d, east), np.einsum("ij,ij->i", d, north)], axis=1)


def _build(latlon: np.ndarray, ei: np.ndarray) -> Graph:
    xyz = latlon_to_xyz(latlon[:, 0], latlon[:, 1])
    return Graph(xyz, latlon, ei.astype(np.int64), _edge_attr(xyz, xyz, ei, latlon))


def knn_graph(latlon: np.ndarray, k: int) -> Graph:
    """Connect every node to its ``k`` nearest neighbours (edges point neighbour -> node)."""
    if not 1 <= k < len(latlon):
        raise ValueError("k must satisfy 1 <= k < n_nodes")
    xyz = latlon_to_xyz(latlon[:, 0], latlon[:, 1])
    _, idx = cKDTree(xyz).query(xyz, k=k + 1)
    receivers = np.repeat(np.arange(len(latlon)), k)
    senders = idx[:, 1:].ravel()
    return _build(latlon, np.stack([senders, receivers]))


def radius_graph(latlon: np.ndarray, radius_km: float) -> Graph:
    """Connect all node pairs closer than ``radius_km`` (great-circle)."""
    xyz = latlon_to_xyz(latlon[:, 0], latlon[:, 1])
    chord = 2.0 * np.sin(radius_km / (2.0 * EARTH_RADIUS_KM))
    pairs = cKDTree(xyz).query_pairs(chord, output_type="ndarray")
    ei = np.concatenate([pairs.T, pairs.T[::-1]], axis=1) if len(pairs) else np.zeros((2, 0), dtype=np.int64)
    return _build(latlon, ei)


def latlon_grid_graph(grid: GridSpec) -> Graph:
    """8-neighbour mesh over a regular lat/lon grid (node index = row * nlon + col)."""
    lon2d, lat2d = np.meshgrid(grid.lons, grid.lats)
    latlon = np.stack([lat2d.ravel(), lon2d.ravel()], axis=1)
    ii, jj = np.meshgrid(np.arange(grid.nlat), np.arange(grid.nlon), indexing="ij")
    src, dst = [], []
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            if di == 0 and dj == 0:
                continue
            ni, nj = ii + di, jj + dj
            valid = (ni >= 0) & (ni < grid.nlat)
            if grid.is_global_lon:
                nj = nj % grid.nlon
            else:
                valid &= (nj >= 0) & (nj < grid.nlon)
            src.append((ii * grid.nlon + jj)[valid])
            dst.append((ni * grid.nlon + nj)[valid])
    return _build(latlon, np.stack([np.concatenate(src), np.concatenate(dst)]))


def icosahedral_mesh(level: int) -> Graph:
    """Icosahedron subdivided ``level`` times (level 0 = 12 nodes; level 6 = 40 962 nodes)."""
    if level < 0:
        raise ValueError("level must be >= 0")
    t = (1.0 + np.sqrt(5.0)) / 2.0
    verts = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
             (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    v = np.array(verts, float)
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    faces = np.array([
        (0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
        (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5),
        (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)])
    verts_list = [row for row in v]

    def midpoint(a: int, b: int, cache: dict[tuple[int, int], int]) -> int:
        key = (min(a, b), max(a, b))
        if key not in cache:
            m = verts_list[a] + verts_list[b]
            verts_list.append(m / np.linalg.norm(m))
            cache[key] = len(verts_list) - 1
        return cache[key]

    for _ in range(level):
        cache: dict[tuple[int, int], int] = {}
        new_faces = []
        for a, b, c in faces:
            ab, bc, ca = midpoint(a, b, cache), midpoint(b, c, cache), midpoint(c, a, cache)
            new_faces += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        faces = np.array(new_faces)
    xyz = np.array(verts_list)
    und = np.unique(np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1), axis=0)
    ei = np.concatenate([und.T, und.T[::-1]], axis=1)
    latlon = xyz_to_latlon(xyz)
    return Graph(xyz, latlon, ei.astype(np.int64), _edge_attr(xyz, xyz, ei, latlon))


def grid_to_mesh_edges(grid_latlon: np.ndarray, mesh: Graph, k: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """Bipartite edges ``grid -> mesh`` (each grid node to its k nearest mesh nodes) and their attributes."""
    gx = latlon_to_xyz(grid_latlon[:, 0], grid_latlon[:, 1])
    _, idx = cKDTree(mesh.xyz).query(gx, k=k)
    idx = idx.reshape(len(grid_latlon), k)
    senders = np.repeat(np.arange(len(grid_latlon)), k)
    ei = np.stack([senders, idx.ravel()]).astype(np.int64)
    return ei, _edge_attr(gx, mesh.xyz, ei, grid_latlon)
