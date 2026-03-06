# -*- coding: utf-8 -*-
from qgis.gui import QgsMapToolEmitPoint
from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject

class RouteMapTool(QgsMapToolEmitPoint):
    """
    Minimal map tool for picking two points:
      - first click: source
      - second click: destination
    Emits: pointPicked(kind, lat, lon)
      kind is "source" or "destination"
    """
    def __init__(self, canvas, callback):
        super().__init__(canvas)
        self.canvas = canvas
        self._callback = callback
        self._count = 0

    def reset(self):
        self._count = 0

    def canvasReleaseEvent(self, event):
        point_map = self.toMapCoordinates(event.pos())

        # Transform to EPSG:4326 (WGS84) for WRT
        src_crs = self.canvas.mapSettings().destinationCrs()
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        xform = QgsCoordinateTransform(src_crs, wgs84, QgsProject.instance())
        point_wgs = xform.transform(point_map)

        lon = float(point_wgs.x())
        lat = float(point_wgs.y())

        kind = "source" if self._count == 0 else "destination"
        self._count += 1

        # Callback into the dialog
        if self._callback:
            self._callback(kind, lat, lon)