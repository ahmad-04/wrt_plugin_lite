# -*- coding: utf-8 -*-
"""
Route Visualiser for WRT Plugin Lite
--------------------------------------
Loads a WRT output JSON route into QGIS as two styled layers:
  1. A LineString layer connecting all waypoints (the route path)
  2. A Point layer with one feature per waypoint, coloured by speed

WRT JSON structure notes:
  - File is a valid GeoJSON FeatureCollection with Point geometries
  - Every numeric property is nested: {"value": <float>, "unit": "<str>"}
  - 15 waypoints typical; coordinates are [lon, lat]

Usage:
    from .route_visualiser import RouteVisualiser
    rv = RouteVisualiser()
    line_layer, point_layer = rv.load_route("/path/to/min_time_route.json")
    summary = rv.get_route_summary(point_layer)
"""

import json

from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsField,
    QgsFields,
    QgsGraduatedSymbolRenderer,
    QgsRendererRange,
    QgsSymbol,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QMetaType
from qgis.PyQt.QtGui import QColor


# ---------------------------------------------------------------------------
# Colour ramps
# ---------------------------------------------------------------------------

# Speed: red (slow) -> yellow -> green (fast)
SPEED_RAMP = [
    (0.0,  QColor("#d73027")),
    (0.25, QColor("#fc8d59")),
    (0.5,  QColor("#fee08b")),
    (0.75, QColor("#91cf60")),
    (1.0,  QColor("#1a9850")),
]

# Fuel: green (low) -> yellow -> red (high)
FUEL_RAMP = [
    (0.0,  QColor("#1a9850")),
    (0.25, QColor("#91cf60")),
    (0.5,  QColor("#fee08b")),
    (0.75, QColor("#fc8d59")),
    (1.0,  QColor("#d73027")),
]

# All numeric properties the WRT writes, with their units for display
WRT_NUMERIC_PROPS = [
    ("speed",                 "m/s"),
    ("fuel_consumption",      "t/h"),
    ("engine_power",          "kW"),
    ("wave_height",           "m"),
    ("wave_period",           "s"),
    ("wind_resistance",       "N"),
    ("wave_resistance",       "N"),
    ("pressure",              "Pa"),
    ("air_temperature",       "C"),
    ("water_temperature",     "C"),
    ("u_wind_speed",          "m/s"),
    ("v_wind_speed",          "m/s"),
    ("u_currents",            "m/s"),
    ("v_currents",            "m/s"),
]


def _interpolate_colour(ramp, fraction):
    """Linearly interpolate a colour from a ramp at position fraction [0,1]."""
    fraction = max(0.0, min(1.0, fraction))
    for i in range(len(ramp) - 1):
        t0, c0 = ramp[i]
        t1, c1 = ramp[i + 1]
        if t0 <= fraction <= t1:
            f = (fraction - t0) / (t1 - t0) if (t1 - t0) > 0 else 0
            r = int(c0.red()   + f * (c1.red()   - c0.red()))
            g = int(c0.green() + f * (c1.green() - c0.green()))
            b = int(c0.blue()  + f * (c1.blue()  - c0.blue()))
            return QColor(r, g, b)
    return ramp[-1][1]


def _build_graduated_renderer(layer, field, ramp, n_classes=5):
    """
    Build a QgsGraduatedSymbolRenderer for `field` using equal intervals.
    Returns None if the field is missing or has no usable values.
    """
    field_idx = layer.fields().indexOf(field)
    if field_idx == -1:
        return None

    values = []
    for feat in layer.getFeatures():
        v = feat[field]
        if v is not None:
            try:
                values.append(float(v))
            except (TypeError, ValueError):
                pass

    if len(values) < 2:
        return None

    min_val = min(values)
    max_val = max(values)
    if min_val == max_val:
        max_val = min_val + 1.0

    step = (max_val - min_val) / n_classes
    ranges = []

    for i in range(n_classes):
        lower  = min_val + i * step
        upper  = min_val + (i + 1) * step
        colour = _interpolate_colour(ramp, (i + 0.5) / n_classes)

        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        symbol.setColor(colour)
        symbol.setSize(4.0)

        ranges.append(QgsRendererRange(
            lower, upper, symbol,
            f"{lower:.3f} - {upper:.3f}"
        ))

    renderer = QgsGraduatedSymbolRenderer(field, ranges)
    return renderer


def _extract_value(prop):
    """
    WRT properties are either {"value": x, "unit": y} dicts or plain scalars.
    Always returns a plain float, or None if missing/sentinel (-99).
    """
    if isinstance(prop, dict):
        v = prop.get("value")
    else:
        v = prop

    if v is None:
        return None
    try:
        f = float(v)
        # WRT uses -99 as a sentinel for "not available"
        return None if f == -99.0 else f
    except (TypeError, ValueError):
        return None


class RouteVisualiser:
    """
    Parses a WRT output JSON file and creates two QGIS memory layers:

    line_layer  -- single LineString connecting all waypoints in order,
                   styled with a solid blue stroke.

    point_layer -- one Point per waypoint with all WRT numeric properties
                   as flat float attributes, graduated-coloured by speed.
    """

    def load_route(self, json_path, style_field="speed"):
        """
        Parse the WRT JSON and add a line + point layer to the QGIS project.

        Parameters
        ----------
        json_path : str
            Path to the WRT output JSON (e.g. min_time_route.json).
        style_field : str
            Property to colour the point layer by. Defaults to "speed".

        Returns
        -------
        tuple (QgsVectorLayer, QgsVectorLayer)
            (line_layer, point_layer) -- both added to QgsProject.
            Returns (None, None) on any parse error.
        """
        # Parse JSON
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None, None

        features = data.get("features", [])
        if not features:
            return None, None

        # Build field definitions for the point layer
        qgs_fields = QgsFields()
        qgs_fields.append(QgsField("time", QMetaType.Type.QString))
        for prop_name, _ in WRT_NUMERIC_PROPS:
            qgs_fields.append(QgsField(prop_name, QMetaType.Type.Double))

        # Collect waypoint coordinates and attribute rows
        coords    = []
        attr_rows = []

        for feat in features:
            geom = feat.get("geometry", {})
            if geom.get("type") != "Point":
                continue

            lon, lat = geom["coordinates"]
            coords.append(QgsPointXY(lon, lat))

            props = feat.get("properties", {})
            row = [props.get("time", "")]
            for prop_name, _ in WRT_NUMERIC_PROPS:
                row.append(_extract_value(props.get(prop_name)))
            attr_rows.append(row)

        if len(coords) < 2:
            return None, None

        # ---- LINE LAYER -------------------------------------------------
        line_layer = QgsVectorLayer(
            "LineString?crs=EPSG:4326", "WRT Route (line)", "memory"
        )
        line_layer.startEditing()
        line_feat = QgsFeature()
        line_feat.setGeometry(QgsGeometry.fromPolylineXY(coords))
        line_layer.addFeature(line_feat)
        line_layer.commitChanges()

        # Style: solid blue, 1.5px width
        line_sym = line_layer.renderer().symbol()
        line_sym.setColor(QColor("#1a6faf"))
        line_sym.setWidth(1.5)
        line_layer.triggerRepaint()

        # ---- POINT LAYER ------------------------------------------------
        point_layer = QgsVectorLayer(
            "Point?crs=EPSG:4326", "WRT Route (waypoints)", "memory"
        )
        pr = point_layer.dataProvider()
        pr.addAttributes(qgs_fields)
        point_layer.updateFields()

        point_layer.startEditing()
        for pt, attrs in zip(coords, attr_rows):
            feat = QgsFeature(qgs_fields)
            feat.setGeometry(QgsGeometry.fromPointXY(pt))
            feat.setAttributes(attrs)
            point_layer.addFeature(feat)
        point_layer.commitChanges()

        # Apply graduated renderer
        available = [f.name() for f in point_layer.fields()]
        if style_field not in available:
            style_field = "speed" if "speed" in available else None

        if style_field:
            ramp = FUEL_RAMP if style_field == "fuel_consumption" else SPEED_RAMP
            renderer = _build_graduated_renderer(point_layer, style_field, ramp)
            if renderer:
                point_layer.setRenderer(renderer)

        # Add line first so points render on top
        QgsProject.instance().addMapLayer(line_layer)
        QgsProject.instance().addMapLayer(point_layer)

        return line_layer, point_layer

    def get_route_summary(self, point_layer):
        """
        Return basic statistics from a loaded waypoint layer.

        Returns
        -------
        dict with keys:
            waypoints         int
            speed_min         float or None   (m/s)
            speed_max         float or None
            speed_mean        float or None
            fuel_total        float or None   (t/h summed)
            engine_power_mean float or None   (kW)
        """
        if point_layer is None or not point_layer.isValid():
            return {}

        summary = {"waypoints": point_layer.featureCount()}

        def _collect(field):
            idx = point_layer.fields().indexOf(field)
            if idx == -1:
                return []
            vals = []
            for feat in point_layer.getFeatures():
                v = feat[field]
                if v is not None:
                    try:
                        vals.append(float(v))
                    except (TypeError, ValueError):
                        pass
            return vals

        speeds = _collect("speed")
        if speeds:
            summary["speed_min"]  = round(min(speeds), 3)
            summary["speed_max"]  = round(max(speeds), 3)
            summary["speed_mean"] = round(sum(speeds) / len(speeds), 3)
        else:
            summary["speed_min"] = summary["speed_max"] = summary["speed_mean"] = None

        fuels = _collect("fuel_consumption")
        summary["fuel_total"] = round(sum(fuels), 3) if fuels else None

        powers = _collect("engine_power")
        summary["engine_power_mean"] = (
            round(sum(powers) / len(powers), 1) if powers else None
        )

        return summary