# -*- coding: utf-8 -*-
"""
WRT Visualisation Panel
------------------------
Standalone dialog (separate from the config wizard) that lets users
load and visualise WRT route JSON files and Copernicus Marine NetCDF
weather data directly — without going through the configuration wizard.

Opened via a second toolbar button in wrt_plugin_lite.py.
"""

import os

from qgis.PyQt import uic
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox
from qgis.utils import iface

from .route_visualiser import RouteVisualiser
from .weather_visualiser import WeatherVisualiser

FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "vis_panel_dialog_base.ui")
)

# Mapping from comboStyleField index to RouteVisualiser field name
STYLE_FIELD_MAP = {
    0: "speed",
    1: "fuel_consumption",
    2: "engine_power",
    3: "wave_height",
}


class VisPanelDialog(QtWidgets.QDialog, FORM_CLASS):
    """
    Two-tab visualisation panel:
      Tab 1 — Route  : load WRT JSON, pick colour field, show stats
      Tab 2 — Weather: load NetCDF, pick variable + time step, show stats
    """

    def __init__(self, parent=None):
        super(VisPanelDialog, self).__init__(parent)
        self.setupUi(self)

        self._route_visualiser   = RouteVisualiser()
        self._weather_visualiser = WeatherVisualiser()

        # State
        self._weather_nc_path  = None
        self._weather_vars     = []   # list of (name, label, unit)
        self._last_route_layer = None
        self._last_weather_layer = None

        self._connect_signals()

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------
    def _connect_signals(self):
        # Route tab
        self.btnBrowseRoute.clicked.connect(self._browse_route)
        self.btnLoadRoute.clicked.connect(self._load_route)
        self.comboStyleField.currentIndexChanged.connect(self._restyle_route)

        # Weather tab
        self.btnBrowseWeatherFile.clicked.connect(self._browse_weather)
        self.comboVariable.currentIndexChanged.connect(self._on_variable_changed)
        self.btnLoadWeatherLayer.clicked.connect(self._load_weather)

        # Close
        self.btnClose.clicked.connect(self.close)

    # ------------------------------------------------------------------
    # Route tab
    # ------------------------------------------------------------------
    def _browse_route(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select WRT Route JSON",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        if path:
            self.lineRouteFile.setText(path)

    def _load_route(self):
        path = self.lineRouteFile.text().strip()
        if not path:
            QMessageBox.warning(self, "No file", "Please select a route JSON file.")
            return

        if not os.path.isfile(path):
            QMessageBox.warning(self, "Not found", f"File not found:\n{path}")
            return

        # Get selected style field
        style_field = STYLE_FIELD_MAP.get(
            self.comboStyleField.currentIndex(), "speed"
        )

        line_layer, point_layer = self._route_visualiser.load_route(
            path, style_field=style_field
        )

        if point_layer is None:
            QMessageBox.warning(
                self,
                "Load Failed",
                "Could not load route.\n"
                "Make sure this is a valid WRT output JSON file."
            )
            return

        self._last_route_layer = point_layer
        self._update_route_stats(point_layer)

    def _restyle_route(self):
        """Re-apply symbology if style field changes after loading."""
        if self._last_route_layer is None:
            return
        # Just reload — simplest approach
        path = self.lineRouteFile.text().strip()
        if path and os.path.isfile(path):
            self._load_route()

    def _update_route_stats(self, point_layer):
        summary = self._route_visualiser.get_route_summary(point_layer)
        if not summary:
            self.labelRouteStats.setText("Could not compute statistics.")
            return

        lines = []
        lines.append(f"Waypoints: {summary.get('waypoints', '?')}")

        if summary.get("speed_mean") is not None:
            lines.append(
                f"Speed:  min {summary['speed_min']} m/s  |  "
                f"max {summary['speed_max']} m/s  |  "
                f"mean {summary['speed_mean']} m/s"
            )
        if summary.get("fuel_total") is not None:
            lines.append(f"Total fuel consumption:  {summary['fuel_total']} t/h")
        if summary.get("engine_power_mean") is not None:
            lines.append(f"Mean engine power:  {summary['engine_power_mean']} kW")

        self.labelRouteStats.setText("\n".join(lines))

    # ------------------------------------------------------------------
    # Weather tab
    # ------------------------------------------------------------------
    def _browse_weather(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Copernicus Marine NetCDF",
            "",
            "NetCDF Files (*.nc);;All Files (*)"
        )
        if not path:
            return

        self.lineWeatherFile.setText(path)
        self._weather_nc_path = path
        self._load_variable_list(path)

    def _load_variable_list(self, nc_path):
        """Populate the variable combo from the NetCDF file."""
        self.comboVariable.blockSignals(True)
        self.comboVariable.clear()

        self._weather_vars = self._weather_visualiser.get_available_variables(nc_path)

        if not self._weather_vars:
            QMessageBox.warning(
                self,
                "No variables found",
                "Could not read any known variables from this file.\n"
                "Make sure it is a Copernicus Marine NetCDF."
            )
            self.comboVariable.blockSignals(False)
            return

        for var_name, label, unit in self._weather_vars:
            self.comboVariable.addItem(f"{label} ({unit})", userData=var_name)

        # Update time step range
        n_steps = self._weather_visualiser.get_time_steps(nc_path)
        self.spinTimeStep.setMaximum(max(0, n_steps - 1))
        self.labelTimeStepMax.setText(f"of {n_steps}")

        self.comboVariable.blockSignals(False)

    def _on_variable_changed(self, index):
        """Update time step max when variable changes (future: per-variable)."""
        pass

    def _load_weather(self):
        if not self._weather_nc_path:
            QMessageBox.warning(
                self, "No file", "Please select a NetCDF file first."
            )
            return

        var_name = self.comboVariable.currentData()
        if not var_name:
            QMessageBox.warning(
                self, "No variable", "Please select a variable."
            )
            return

        time_index = self.spinTimeStep.value()

        layer = self._weather_visualiser.load_variable(
            self._weather_nc_path, var_name, time_index=time_index
        )

        if layer is None:
            QMessageBox.warning(
                self,
                "Load Failed",
                f"Could not load variable '{var_name}' at time step {time_index}."
            )
            return

        self._last_weather_layer = layer
        self._update_weather_stats(var_name, time_index)

    def _update_weather_stats(self, var_name, time_index):
        """Compute and display stats for the current map canvas extent."""
        canvas_extent = iface.mapCanvas().extent()

        stats = self._weather_visualiser.compute_bbox_stats(
            self._weather_nc_path, var_name, time_index, canvas_extent
        )

        if not stats:
            self.labelWeatherStats.setText(
                "Layer loaded. Pan/zoom the map then reload to compute stats."
            )
            return

        unit = stats.get("unit", "")
        lines = [
            f"Extent statistics  (time step {time_index}, {stats.get('count', '?')} pixels)",
            f"Min:  {stats['min']} {unit}    "
            f"Max:  {stats['max']} {unit}",
            f"Mean: {stats['mean']} {unit}    "
            f"Std:  {stats['std']} {unit}",
        ]
        self.labelWeatherStats.setText("\n".join(lines))
