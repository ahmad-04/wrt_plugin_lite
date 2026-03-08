# WRT Plugin Lite – QGIS Weather Routing Configuration Wizard

A lightweight **QGIS plugin** for creating configuration files for the **52°North Weather Routing Tool (WRT)**.

The plugin provides a **step-by-step wizard interface** to configure routing parameters, select route points directly from the map, and export a valid **WRT configuration JSON** ready to run with the WRT CLI.

---

# Features

## Interactive Route Selection
Pick **source and destination points directly from the QGIS map canvas**.

## Step-by-Step Configuration Wizard
The plugin guides the user through the routing setup process:

1. **Route Definition**
2. **Time & Algorithm Settings**
3. **Data & Output Configuration**
4. **Configuration Summary**

## WRT-Compatible Configuration Export
Exports a **fully compatible configuration JSON** for:

- Genetic routing algorithm
- Isofuel routing algorithm
- Direct power vessel model

## Weather & Ocean Data Support

Supports two modes:

### Automatic Mode
Weather data is downloaded automatically using **Copernicus Marine** services.

### Manual Mode
Users can supply existing NetCDF datasets:

- Weather data (`WEATHER_DATA`)
- Depth data (`DEPTH_DATA`)
- Courses data (`COURSES_FILE`)

## Vessel Presets

Included vessel models:

- Generic Cargo
- Fast Vessel

Each preset automatically fills the required ship parameters.

---

# Plugin Interface

The wizard consists of four pages.

## Route Page

- Pick **source and destination** from the QGIS map
- View route coordinates in a table
- Clear and reset the route

## Time & Algorithm Page

Configure:

- Departure time
- Optional arrival time
- Forecast horizon
- Forecast resolution
- Routing algorithm
- Vessel preset

## Data & Output Page

Configure:

- Data mode (Automatic / Manual)
- Weather dataset
- Depth dataset
- Courses file
- Output directory

## Summary Page

Displays a full preview of the generated configuration before exporting.

---

# Output

The plugin exports a configuration file:
