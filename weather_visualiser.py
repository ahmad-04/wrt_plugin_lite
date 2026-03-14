# -*- coding: utf-8 -*-
"""
Weather Visualiser for WRT Plugin Lite
----------------------------------------
Loads variables from a Copernicus Marine NetCDF file as styled QGIS
raster layers. Uses GDAL (built into QGIS) — no extra dependencies needed.

NetCDF structure (from actual WRT weather data):
    Dimensions : time=32, depth=1, latitude=38, longitude=94
    Variables  :
        VHM0                              - significant wave height (m)
        VTPK                              - wave peak period (s)
        VMDR                              - wave direction (degrees)
        vtotal, utotal                    - ocean currents (m/s)
        thetao                            - water temperature (C)
        so                                - salinity
        Temperature_surface               - air temperature (C)
        u-component_of_wind_...           - wind U component (m/s)
        v-component_of_wind_...           - wind V component (m/s)
        Pressure_reduced_to_MSL_msl       - pressure (Pa)

Usage:
    from .weather_visualiser import WeatherVisualiser
    wv = WeatherVisualiser()
    variables = wv.get_available_variables(nc_path)
    layer = wv.load_variable(nc_path, "VHM0", time_index=0)
    stats = wv.compute_bbox_stats(nc_path, "VHM0", time_index=0, bbox=iface.mapCanvas().extent())
"""

from osgeo import gdal
from qgis.core import (
    QgsRasterLayer,
    QgsProject,
    QgsSingleBandPseudoColorRenderer,
    QgsColorRampShader,
    QgsRasterShader,
    QgsRectangle,
)
from qgis.PyQt.QtGui import QColor
import os

gdal.UseExceptions()

# ---------------------------------------------------------------------------
# Variable catalogue — maps NetCDF variable name to display info
# ---------------------------------------------------------------------------
VARIABLE_CATALOGUE = {
    "VHM0": {
        "label":      "Significant wave height",
        "unit":       "m",
        "ramp":       "wave_height",
        "depth_dim":  False,
        "wind_dim":   False,
    },
    "VTPK": {
        "label":      "Wave peak period",
        "unit":       "s",
        "ramp":       "period",
        "depth_dim":  False,
        "wind_dim":   False,
    },
    "VMDR": {
        "label":      "Wave direction",
        "unit":       "deg",
        "ramp":       "direction",
        "depth_dim":  False,
        "wind_dim":   False,
    },
    "thetao": {
        "label":      "Water temperature",
        "unit":       "C",
        "ramp":       "temperature",
        "depth_dim":  True,
        "wind_dim":   False,
    },
    "so": {
        "label":      "Salinity",
        "unit":       "PSU",
        "ramp":       "salinity",
        "depth_dim":  True,
        "wind_dim":   False,
    },
    "vtotal": {
        "label":      "Ocean current (N-S)",
        "unit":       "m/s",
        "ramp":       "current",
        "depth_dim":  True,
        "wind_dim":   False,
    },
    "utotal": {
        "label":      "Ocean current (E-W)",
        "unit":       "m/s",
        "ramp":       "current",
        "depth_dim":  True,
        "wind_dim":   False,
    },
    "Temperature_surface": {
        "label":      "Air temperature",
        "unit":       "C",
        "ramp":       "temperature",
        "depth_dim":  False,
        "wind_dim":   False,
    },
    "u-component_of_wind_height_above_ground": {
        "label":      "Wind U component",
        "unit":       "m/s",
        "ramp":       "wind",
        "depth_dim":  False,
        "wind_dim":   True,
    },
    "v-component_of_wind_height_above_ground": {
        "label":      "Wind V component",
        "unit":       "m/s",
        "ramp":       "wind",
        "depth_dim":  False,
        "wind_dim":   True,
    },
    "Pressure_reduced_to_MSL_msl": {
        "label":      "Sea level pressure",
        "unit":       "Pa",
        "ramp":       "pressure",
        "depth_dim":  False,
        "wind_dim":   False,
    },
}

# ---------------------------------------------------------------------------
# Colour ramps per variable type
# ---------------------------------------------------------------------------
COLOUR_RAMPS = {
    "wave_height": [
        (0.0,  QColor("#313695")),
        (0.25, QColor("#74add1")),
        (0.5,  QColor("#fee090")),
        (0.75, QColor("#f46d43")),
        (1.0,  QColor("#a50026")),
    ],
    "temperature": [
        (0.0,  QColor("#313695")),
        (0.25, QColor("#74add1")),
        (0.5,  QColor("#ffffbf")),
        (0.75, QColor("#f46d43")),
        (1.0,  QColor("#a50026")),
    ],
    "wind": [
        (0.0,  QColor("#f7fbff")),
        (0.25, QColor("#9ecae1")),
        (0.5,  QColor("#3182bd")),
        (0.75, QColor("#08519c")),
        (1.0,  QColor("#08306b")),
    ],
    "current": [
        (0.0,  QColor("#f7fcf0")),
        (0.25, QColor("#7bccc4")),
        (0.5,  QColor("#2b8cbe")),
        (0.75, QColor("#0868ac")),
        (1.0,  QColor("#084081")),
    ],
    "pressure": [
        (0.0,  QColor("#fff7fb")),
        (0.25, QColor("#ece7f2")),
        (0.5,  QColor("#74a9cf")),
        (0.75, QColor("#0570b0")),
        (1.0,  QColor("#023858")),
    ],
    "period": [
        (0.0,  QColor("#ffffcc")),
        (0.25, QColor("#a1dab4")),
        (0.5,  QColor("#41b6c4")),
        (0.75, QColor("#2c7fb8")),
        (1.0,  QColor("#253494")),
    ],
    "direction": [
        (0.0,   QColor("#d73027")),
        (0.25,  QColor("#fee08b")),
        (0.5,   QColor("#1a9850")),
        (0.75,  QColor("#4575b4")),
        (1.0,   QColor("#d73027")),
    ],
    "salinity": [
        (0.0,  QColor("#ffffd9")),
        (0.25, QColor("#7fcdbb")),
        (0.5,  QColor("#1d91c0")),
        (0.75, QColor("#225ea8")),
        (1.0,  QColor("#081d58")),
    ],
}


def _build_colour_ramp_shader(ramp_key, min_val, max_val, n_steps=10):
    """Build a QgsColorRampShader from a named ramp between min and max."""
    ramp = COLOUR_RAMPS.get(ramp_key, COLOUR_RAMPS["wave_height"])
    shader = QgsColorRampShader(min_val, max_val)
    shader.setColorRampType(QgsColorRampShader.Type.Interpolated)

    items = []
    for i in range(n_steps + 1):
        frac = i / n_steps
        val  = min_val + frac * (max_val - min_val)

        # Interpolate colour from ramp stops
        colour = ramp[-1][1]
        for j in range(len(ramp) - 1):
            t0, c0 = ramp[j]
            t1, c1 = ramp[j + 1]
            if t0 <= frac <= t1:
                f = (frac - t0) / (t1 - t0) if (t1 - t0) > 0 else 0
                r = int(c0.red()   + f * (c1.red()   - c0.red()))
                g = int(c0.green() + f * (c1.green() - c0.green()))
                b = int(c0.blue()  + f * (c1.blue()  - c0.blue()))
                colour = QColor(r, g, b)
                break

        items.append(QgsColorRampShader.ColorRampItem(val, colour, f"{val:.2f}"))

    shader.setColorRampItemList(items)
    return shader


def _apply_pseudocolour(layer, ramp_key):
    """Apply a pseudocolour renderer to a single-band raster layer."""
    provider = layer.dataProvider()
    stats    = provider.bandStatistics(1)
    min_val  = stats.minimumValue
    max_val  = stats.maximumValue

    if min_val == max_val:
        max_val = min_val + 1.0

    colour_shader = _build_colour_ramp_shader(ramp_key, min_val, max_val)
    raster_shader  = QgsRasterShader()
    raster_shader.setRasterShaderFunction(colour_shader)

    renderer = QgsSingleBandPseudoColorRenderer(provider, 1, raster_shader)
    layer.setRenderer(renderer)
    layer.triggerRepaint()


class WeatherVisualiser:
    """
    Loads a single variable from a Copernicus Marine NetCDF file
    as a styled QGIS raster layer using GDAL (no extra dependencies).
    """

    def get_available_variables(self, nc_path):
        """
        Return list of (variable_name, display_label, unit) tuples
        for variables present in the file that are in our catalogue.

        Parameters
        ----------
        nc_path : str
            Path to the NetCDF file.

        Returns
        -------
        list of (str, str, str)  —  (name, label, unit)
        """
        available = []
        try:
            ds = gdal.Open(nc_path)
            if ds is None:
                return available
            subdatasets = ds.GetSubDatasets()
            ds = None

            for sd_path, sd_desc in subdatasets:
                # Extract variable name from subdataset path
                # Format: NETCDF:"file.nc":variable_name
                parts = sd_path.split(":")
                if len(parts) >= 3:
                    var_name = parts[-1]
                elif len(parts) == 2:
                    var_name = parts[-1]
                else:
                    continue

                if var_name in VARIABLE_CATALOGUE:
                    info = VARIABLE_CATALOGUE[var_name]
                    available.append((
                        var_name,
                        info["label"],
                        info["unit"],
                    ))
        except Exception:
            pass

        return available

    def get_time_steps(self, nc_path):
        """
        Return the number of time steps in the NetCDF file.

        Parameters
        ----------
        nc_path : str

        Returns
        -------
        int — number of time steps (0 on failure)
        """
        try:
            # Open any subdataset to read time dimension
            ds = gdal.Open(nc_path)
            if ds is None:
                return 0
            sds = ds.GetSubDatasets()
            ds = None
            if not sds:
                return 0

            # Open first subdataset and count bands (each = one time step)
            first_ds = gdal.Open(sds[0][0])
            if first_ds is None:
                return 0
            count = first_ds.RasterCount
            first_ds = None
            return count
        except Exception:
            return 0

    def load_variable(self, nc_path, variable_name, time_index=0):
        """
        Load one variable at one time step as a styled QGIS raster layer.

        Parameters
        ----------
        nc_path : str
            Path to the NetCDF file.
        variable_name : str
            Variable name (e.g. "VHM0", "Temperature_surface").
        time_index : int
            Time step index (0-based). Each GDAL band = one time step.

        Returns
        -------
        QgsRasterLayer or None
        """
        # Build GDAL subdataset URI
        # Format: NETCDF:"path/to/file.nc":variable_name
        nc_path_clean = nc_path.replace("\\", "/")
        uri = f'NETCDF:"{nc_path_clean}":{variable_name}'

        info = VARIABLE_CATALOGUE.get(variable_name, {})
        label = info.get("label", variable_name)
        unit  = info.get("unit", "")
        ramp  = info.get("ramp", "wave_height")

        layer_name = f"{label} (t={time_index})"

        # Load as raster layer
        layer = QgsRasterLayer(uri, layer_name)

        if not layer.isValid():
            return None

        # GDAL bands correspond to time steps for 3D variables
        # Select the correct band (1-based in GDAL)
        band = time_index + 1
        total_bands = layer.dataProvider().bandCount()
        if band > total_bands:
            band = 1

        # Apply colour ramp
        _apply_pseudocolour(layer, ramp)

        QgsProject.instance().addMapLayer(layer)
        return layer

    def compute_bbox_stats(self, nc_path, variable_name, time_index, bbox):
        """
        Compute statistics for a variable within a QGIS extent (bounding box)
        at a given time step. Uses GDAL to read the data window.

        Parameters
        ----------
        nc_path : str
        variable_name : str
        time_index : int
        bbox : QgsRectangle
            Spatial extent to compute stats for.

        Returns
        -------
        dict with keys: min, max, mean, std, unit, count
            Returns empty dict on failure.
        """
        try:
            nc_path_clean = nc_path.replace("\\", "/")
            uri = f'NETCDF:"{nc_path_clean}":{variable_name}'

            ds = gdal.Open(uri)
            if ds is None:
                return {}

            gt     = ds.GetGeoTransform()
            band_n = time_index + 1
            if band_n > ds.RasterCount:
                band_n = 1

            band = ds.GetRasterBand(band_n)

            # Convert bbox to pixel coordinates
            x_min = bbox.xMinimum()
            x_max = bbox.xMaximum()
            y_min = bbox.yMinimum()
            y_max = bbox.yMaximum()

            # gt[0]=top-left x, gt[1]=pixel width, gt[3]=top-left y, gt[5]=pixel height (negative)
            col_min = max(0, int((x_min - gt[0]) / gt[1]))
            col_max = min(ds.RasterXSize, int((x_max - gt[0]) / gt[1]) + 1)
            row_min = max(0, int((y_max - gt[3]) / gt[5]))
            row_max = min(ds.RasterYSize, int((y_min - gt[3]) / gt[5]) + 1)

            if col_max <= col_min or row_max <= row_min:
                return {}

            # Read the data window as numpy array
            import numpy as np
            data = band.ReadAsArray(
                col_min, row_min,
                col_max - col_min,
                row_max - row_min
            ).astype(float)

            # Mask nodata
            nodata = band.GetNoDataValue()
            if nodata is not None:
                data = data[data != nodata]

            data = data[np.isfinite(data)]

            if data.size == 0:
                return {}

            info = VARIABLE_CATALOGUE.get(variable_name, {})

            return {
                "min":   round(float(data.min()),  4),
                "max":   round(float(data.max()),  4),
                "mean":  round(float(data.mean()), 4),
                "std":   round(float(data.std()),  4),
                "count": int(data.size),
                "unit":  info.get("unit", ""),
            }

        except Exception:
            return {}