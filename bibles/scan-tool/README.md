# Scan Tool Bible

## Overview
Diagnostic scan tools for automotive ECU diagnostics: Launch X431, Autel, Snap-On, Bosch KTS, Delphi, Tektronix.

## Categories

### 1. OEM-Level Scan Tools
- **Launch X431** — Full OBD2 diagnostics, ECU coding, active tests, bi-directional control
- **Bosch KTS 570/580** — Professional diagnostics, guided fault finding, waveforms
- **Snap-On MODIS** — Advanced diagnostics, graphing, scope integration
- **Delphi DS150E** — OEM-level diagnostics for European vehicles

### 2. Budget/Prosumer
- **Autel MaxiCOM/MaxiSys** — OBD2, ABS, SRS, EPB, oil reset, IMMO
- **BlueDriver** — Bluetooth OBD2, iOS/Android, basic diagnostics
- **Veepeak OBDCheck** — Budget OBD2, real-time data, DTC reader

### 3. Specialist Tools
- **EDC17/MD1/DCM** — ECU-specific diagnostics (diesel engines)
- **Hertz/Technician** — Heavy duty truck diagnostics
- **i-HDS/HDS** — Honda/Acura diagnostics
- **Techstream** — Toyota/Lexus diagnostics

## Protocols
- ISO 9141-2 (K-line)
- ISO 14230-4 (KWP2000)
- ISO 15765-4 (CAN)
- SAE J1850 PWM/VPW
- ISO 9141-2 (L-line)

## OBD2 PIDs
- P0300-P0308 (Misfire)
- P0171/P0174 (System Lean)
- P0420 (Catalyst Efficiency)
- P0442/P0455 (EVAP Leak)
- P0101-P0104 (MAF/MAP)
- P0113/P0114 (IAT)
- P0128 (Coolant Thermostat)

## DTC Structure
- 1st char: P=Powertrain, B=Body, C=Chassis, U=Network
- 2nd char: 0=ISO, 1=Manufacturer, 2=System, 3=Network
- 3rd-4th char: Subsystem code
- 5th char: Specific fault

## Safety
- Always disconnect battery before ECU work
- Note radio codes, throttle adaptation, steering angle reset procedures
- Use appropriate scan tool for vehicle category

## References
- Launch X431 documentation
- EDC17/MD1/DCM specs
- OBD2 standard (ISO 15031-5)
