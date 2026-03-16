# WRT Plugin Lite

A lightweight QGIS plugin that provides a guided configuration wizard for the [52°North Weather Routing Tool (WRT)](https://github.com/52North/WeatherRoutingTool) and a built-in visualisation panel for inspecting WRT output routes and Copernicus Marine weather data directly inside QGIS.

---

## Features

### Configuration Wizard
- Step-by-step dialog for building a WRT `config.runtime.json`
- Interactive route planning — click source, destination, and optional waypoints directly on the QGIS map canvas
- Vessel presets (Generic Cargo, Fast Vessel) with full parameter sets
- Choice of routing algorithm: **Genetic Algorithm** or **Isofuel Algorithm**
- Weather data modes:
  - **Automatic** — Copernicus Marine download managed by WRT
  - **Manual** — point to existing NetCDF files for weather, depth, and courses
- Departure / arrival time scheduling with validation
- Configurable forecast horizon and resolution
- One-click export to `config.runtime.json` ready to pass directly to WRT

### Visualisation Panel

Opened separately after a WRT run to inspect results.

#### Route Tab
- Loads a WRT output GeoJSON (`min_time_route.json` or similar) and adds two QGIS layers:
  - **WRT Route (line)** — a blue LineString connecting all waypoints in order
  - **WRT Route (waypoints)** — a graduated-colour Point layer with all WRT numeric properties as attributes
- Colour-by selector: Speed, Fuel consumption, Engine power, Wave height
- Route statistics summary: waypoint count, speed min/max/mean, total fuel, mean engine power

#### Weather Tab
- Loads any variable from a Copernicus Marine NetCDF file as a styled QGIS raster layer
- Supports 11 variables out of the box (see table below)
- Time step selector — each GDAL band maps to one forecast step
- Live statistics for the current map canvas extent: min, max, mean, std dev, cell count

---

## Supported Weather Variables

| Variable | Description | Unit |
|---|---|---|
| `VHM0` | Significant wave height | m |
| `VTPK` | Wave peak period | s |
| `VMDR` | Wave direction | degrees |
| `thetao` | Water temperature | °C |
| `so` | Salinity | PSU |
| `vtotal` | Ocean current (N–S) | m/s |
| `utotal` | Ocean current (E–W) | m/s |
| `Temperature_surface` | Air temperature | °C |
| `u-component_of_wind_height_above_ground` | Wind U component | m/s |
| `v-component_of_wind_height_above_ground` | Wind V component | m/s |
| `Pressure_reduced_to_MSL_msl` | Sea level pressure | Pa |

---

## Requirements

- **QGIS** 3.x (tested on 3.28+)
- **GDAL** — bundled with QGIS; used for NetCDF raster loading
- **numpy** — bundled with QGIS; used for bbox statistics
- Python packages: `qgis.core`, `qgis.PyQt` — both available in the QGIS Python environment
- A working installation of the [52°North Weather Routing Tool](https://github.com/52North/WeatherRoutingTool) to generate route outputs (not required for the visualisation panel alone)

---

## Installation

1. Clone or download this repository:
   ```bash
   git clone https://github.com/ahmad-04/wrt_plugin_lite.git
   ```

2. Copy the plugin folder into your QGIS plugins directory:

   | OS | Path |
   |---|---|
   | Linux | `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/` |
   | Windows | `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\` |
   | macOS | `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/` |

3. In QGIS: **Plugins → Manage and Install Plugins → Installed**, find **WRT Plugin Lite**, and enable it.

4. The plugin toolbar button and menu entry will appear under **Plugins → WRT Plugin Lite**.

---

## Usage

### 1. Configuring a WRT Run

1. Open the plugin from **Plugins → WRT Plugin Lite → Configure WRT Run**.
2. Work through the wizard pages using **Next** and **Back**:
   - **Route** — click **Pick Route Points** to select source, optional intermediate waypoints, and destination on the map canvas
   - **Timing** — set departure time; optionally constrain to an arrival time
   - **Vessel** — choose a vessel preset
   - **Algorithm** — choose Genetic or Isofuel; set forecast horizon and resolution
   - **Data** — choose Automatic or Manual data mode; in Manual mode, browse to your NetCDF files and output directory
   - **Summary** — review all settings before export
3. Click **Export Config** to save `config.runtime.json`.
4. Run WRT externally using the exported config.

### 2. Visualising Results

1. Open **Plugins → WRT Plugin Lite → Visualisation Panel**.
2. **Route tab:**
   - Browse to the WRT output JSON (e.g. `min_time_route.json`)
   - Select the property to colour waypoints by
   - Click **Load Route to QGIS** — a line layer and a point layer are added to the project
   - Route statistics appear in the panel
3. **Weather tab:**
   - Browse to your Copernicus Marine NetCDF file
   - Select a variable from the dropdown
   - Set the time step index (0 = first forecast step)
   - Click **Load Weather Layer** — a styled raster layer is added to the project
   - Pan/zoom the map canvas and the statistics box updates for the visible extent

---

## Project Structure

```
wrt_plugin_lite/
├── wrt_plugin_lite.py              # Plugin entry point; registers toolbar action
├── wrt_plugin_lite_dialog.py       # Configuration wizard dialog (logic)
├── wrt_plugin_lite_dialog_base.ui  # Configuration wizard UI layout
├── route_map_tool.py               # Custom QGIS map tool for clicking waypoints
├── vis_panel_dialog.py             # Visualisation panel dialog (logic)
├── vis_panel_dialog_base.py        # Visualisation panel UI layout (auto-generated)
├── route_visualiser.py             # Loads WRT JSON → line + point layers
├── weather_visualiser.py           # Loads NetCDF variables → styled raster layers
├── metadata.txt                    # QGIS plugin metadata
└── __init__.py
```

---

## WRT Output JSON Format

The plugin expects standard WRT GeoJSON output — a `FeatureCollection` of `Point` features where every numeric property is a nested object:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "Point", "coordinates": [lon, lat] },
      "properties": {
        "time": "2026-03-04T06:00:00",
        "speed":            { "value": 6.2,  "unit": "m/s" },
        "fuel_consumption": { "value": 1.45, "unit": "t/h" },
        "engine_power":     { "value": 4200, "unit": "kW"  },
        "wave_height":      { "value": 1.8,  "unit": "m"   }
      }
    }
  ]
}
```

Sentinel value `-99` is treated as "not available" and stored as `NULL` in the attribute table.

---

## Developer Notes

### Adding a New Styled Field

To colour waypoints by an additional WRT property, add an entry to `WRT_NUMERIC_PROPS` in `route_visualiser.py`:

```python
WRT_NUMERIC_PROPS = [
    ...
    ("my_new_property", "unit"),
]
```

Then add the corresponding combo box item in `vis_panel_dialog_base.py` and handle it in the visualisation panel dialog.

### Adding a New Weather Variable

Add an entry to `VARIABLE_CATALOGUE` in `weather_visualiser.py`:

```python
VARIABLE_CATALOGUE["my_var"] = {
    "label":     "My Variable",
    "unit":      "unit",
    "ramp":      "temperature",   # any key from COLOUR_RAMPS
    "depth_dim": False,
    "wind_dim":  False,
}
```

Available colour ramps: `wave_height`, `temperature`, `wind`, `current`, `pressure`, `period`, `direction`, `salinity`.

---

## License

Copyright © 2026 Muhammad Ahmad. See `LICENSE` for details.

## Contact

Muhammad Ahmad — mahmada2904@gmail.com
