"""Utilities for working with constituency boundary datasets."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from shapely.geometry import Point, shape
from shapely.prepared import prep

logger = logging.getLogger(__name__)


@dataclass
class BoundaryFeature:
    """Represents a single boundary feature with prepared geometry."""

    properties: Dict[str, Any]
    minx: float
    miny: float
    maxx: float
    maxy: float
    prepared_geometry: Any

    def contains(self, point: Point) -> bool:
        if point.x < self.minx or point.x > self.maxx:
            return False
        if point.y < self.miny or point.y > self.maxy:
            return False
        return self.prepared_geometry.contains(point)


class BoundaryIndex:
    """Spatial index over Wahlkreis polygon features."""

    def __init__(self, features: Iterable[Dict[str, Any]]):
        self._features = []
        for feature in features:
            geometry_mapping = feature.get("geometry")
            properties = feature.get("properties", {})
            if not geometry_mapping:
                continue

            geometry = shape(geometry_mapping)
            if not geometry.is_valid:
                geometry = geometry.buffer(0)

            minx, miny, maxx, maxy = geometry.bounds
            prepared = prep(geometry)

            self._features.append(
                BoundaryFeature(
                    properties=properties,
                    minx=minx,
                    miny=miny,
                    maxx=maxx,
                    maxy=maxy,
                    prepared_geometry=prepared,
                )
            )

        logger.debug("Loaded %s boundary features", len(self._features))

    @classmethod
    def from_geojson(cls, path: Path) -> "BoundaryIndex":
        logger.info("Loading constituency boundaries from %s", path)
        with path.open("r", encoding="utf-8") as geojson_file:
            data = json.load(geojson_file)

        features = data.get("features", [])
        if not features:
            logger.warning("Boundary dataset at %s contains no features", path)
        return cls(features)

    def lookup(self, latitude: float, longitude: float) -> Optional[Dict[str, Any]]:
        """Return feature properties for the polygon containing the given point."""
        point = Point(longitude, latitude)
        for feature in self._features:
            if feature.contains(point):
                return feature.properties
        return None


class BoundaryRepository:
    """Lazy loader that caches the boundary index in memory."""

    _index: Optional[BoundaryIndex] = None

    @classmethod
    def configure(cls, boundary_path: Path) -> None:
        cls._index = BoundaryIndex.from_geojson(boundary_path)

    @classmethod
    def get_index(cls, boundary_path: Optional[Path]) -> Optional[BoundaryIndex]:
        if boundary_path is None:
            logger.debug("No boundary dataset configured")
            return None

        if cls._index is None:
            if not boundary_path.exists():
                logger.warning("Boundary dataset %s not found", boundary_path)
                return None
            cls.configure(boundary_path)

        return cls._index
