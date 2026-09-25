# Scan Tool Bible — World-Class Diagnostic Reference

## Quick Reference Search Bar
```
Search: [PID/DTC/Sensor] → jump to section
```

### Index
1. OBD2 PIDs — Standard Running Data & Thresholds
2. DTC Dictionary — P/B/C/U Codes
3. Sensor Modules — What It Does / How It Works / How to Test / Standard Data / Thresholds
4. Scan Tool Categories — Launch X431, Autel, Snap-On, Bosch, Delphi, Tektronix
5. Protocols — ISO 9141-2, ISO 14230-4, ISO 15765-4, SAE J1850 PWM/VPW
6. Appendix — Non-Conversant Folk Reference
7. Voice Q&A — Higher Paid Tier

---

## 1. OBD2 PIDs — Standard Running Data & Thresholds

| PID | Description | Standard Value | Threshold (Low) | Threshold (High) | Unit |
|-----|-------------|----------------|-----------------|------------------|------|
| P0300 | Random/Multiple Cylinder Misfire | 0 | >0 | >0 | Counts |
| P0301-P0308 | Cylinder X Misfire | 0 | >0 | >0 | Counts |
| P0171 | System Lean (Bank 1) | 0 | >0 | >0 | Counts |
| P0174 | System Lean (Bank 2) | 0 | >0 | >0 | Counts |
| P0420 | Catalyst Efficiency | 0 | >0 | >0 | Counts |
| P0442 | EVAP Leak (small) | 0 | >0 | >0 | Counts |
| P0455 | EVAP Leak (large) | 0 | >0 | >0 | Counts |
| P0101 | MAF Circuit Range/Performance | 2.5-4.0 g/s (idle) | <1.0 g/s | >8.0 g/s (idle) | g/s |
| P0102 | MAF Circuit Low Input | 2.5-4.0 g/s (idle) | <1.0 g/s | — | g/s |
| P0103 | MAF Circuit High Input | 2.5-4.0 g/s (idle) | — | >8.0 g/s | g/s |
| P0113 | IAT Circuit High Input | 20-30°C (ambient) | >60°C | >100°C | °C |
| P0114 | IAT Circuit Low Input | 20-30°C (ambient) | <-20°C | — | °C |
| P0128 | Coolant Thermostat | 85-95°C (operating) | <70°C | >105°C | °C |
| P0101-P0104 | MAF/MAP range | 2.5-4.0 g/s (idle) | <1.0 g/s | >8.0 g/s | g/s |

---

## 2. DTC Dictionary — P/B/C/U Codes

| Prefix | System | Description | Common Causes |
|--------|--------|-------------|---------------|
| P | Powertrain | Engine, transmission | Faulty sensor, wiring, ECU |
| B | Body | Airbags, climate, windows | Sensor failure, module fault |
| C | Chassis | ABS, ESC, suspension | Wheel speed sensor, ESC module |
| U | Network | CAN bus, communication | Wiring fault, module not responding |

### DTC Structure
- 1st char: P/B/C/U
- 2nd char: 0=ISO, 1=Manufacturer, 2=System, 3=Network
- 3rd-4th char: Subsystem code
- 5th char: Specific fault

### Common P-Codes
| Code | Description | Standard Threshold | Test Procedure |
|------|-------------|-------------------|----------------|
| P0171 | System Lean (Bank 1) | >0 counts | Check MAF, vacuum leaks, fuel pressure |
| P0174 | System Lean (Bank 2) | >0 counts | Check MAF, vacuum leaks, fuel pressure |
| P0300 | Random Misfire | >0 counts | Check spark plugs, coils, fuel injectors |
| P0420 | Catalyst Efficiency | >0 counts | Check O2 sensors, catalytic converter |
| P0442 | EVAP Leak (small) | >0 counts | Check gas cap, EVAP lines |
| P0455 | EVAP Leak (large) | >0 counts | Check EVAP canister, purge valve |
| P0101 | MAF Range | <1.0 or >8.0 g/s | Check MAF sensor, air filter, intake |
| P0113 | IAT High | >100°C | Check IAT sensor, wiring |
| P0128 | Coolant Thermostat | <70°C | Check thermostat, coolant level |

---

## 3. Sensor Modules — What It Does / How It Works / How to Test / Standard Data / Thresholds

### 3.1 MAF (Mass Air Flow) Sensor
- **What it does**: Measures air intake mass flow rate for fuel calculation
- **How it works**: Hot wire cooled by airflow; resistance change = air mass
- **How to test**: Scan tool → PID P0101 (g/s); compare to standard (2.5-4.0 g/s idle)
- **Standard running data**: 2.5-4.0 g/s (idle), 50-150 g/s (2500 RPM)
- **Thresholds**: Low <1.0 g/s, High >8.0 g/s (idle)
- **Failure modes**: Dirty sensor, wiring fault, ECU fault

### 3.2 IAT (Intake Air Temperature) Sensor
- **What it does**: Measures intake air temperature
- **How it works**: Thermistor — resistance changes with temperature
- **How to test**: Scan tool → PID P0113/P0114; compare to ambient
- **Standard running data**: 20-30°C (ambient), 40-60°C (operating)
- **Thresholds**: High >100°C, Low <-20°C
- **Failure modes**: Faulty sensor, wiring short, ECU fault

### 3.3 O2 (Oxygen) Sensor
- **What it does**: Measures exhaust O2 for fuel trim adjustment
- **How it works**: Zirconia cell — voltage proportional to O2 difference
- **How to test**: Scan tool → PID 0130-0167 (upstream/downstream); voltage 0.1-0.9V
- **Standard running data**: 0.1-0.9V (switching), 0.45V (steady state)
- **Thresholds**: Low <0.1V, High >0.9V
- **Failure modes**: Catalyst coating, wiring fault, ECU fault

### 3.4 Coolant Temperature Sensor (ECT)
- **What it does**: Measures engine coolant temperature
- **How it works**: Thermistor — resistance decreases with temperature
- **How to test**: Scan tool → PID 0115-0118; compare to infrared thermometer
- **Standard running data**: 85-95°C (operating), 20-30°C (cold start)
- **Thresholds**: High >105°C, Low <70°C (operating)
- **Failure modes**: Faulty sensor, wiring short, ECU fault

### 3.5 MAP (Manifold Absolute Pressure) Sensor
- **What it does**: Measures intake manifold pressure for load calculation
- **How it works**: Piezoresistive — voltage proportional to pressure
- **How to test**: Scan tool → PID 0110; compare to barometric pressure
- **Standard running data**: 20-30 kPa (idle), 80-100 kPa (WOT)
- **Thresholds**: Low <10 kPa (idle), High >120 kPa (idle)
- **Failure modes**: Vacuum leak, wiring fault, ECU fault

### 3.6 TPS (Throttle Position Sensor)
- **What it does**: Measures throttle valve angle
- **How it works**: Potentiometer — voltage proportional to throttle angle
- **How to test**: Scan tool → PID 0121; 0% (closed) = 0.5V, 100% (WOT) = 4.5V
- **Standard running data**: 0.5V (closed), 4.5V (WOT), 1.0-4.0V (partial)
- **Thresholds**: Low <0.2V, High >4.8V
- **Failure modes**: Wiring fault, ECU fault, mechanical binding

### 3.7 CKP (Crankshaft Position) Sensor
- **What it does**: Measures crankshaft position and RPM
- **How it works**: Reluctor wheel + magnetic sensor — AC voltage pulses
- **How to test**: Oscilloscope → AC waveform; scan tool → RPM
- **Standard running data**: 600-800 RPM (idle), 6000-7000 RPM (WOT)
- **Thresholds**: Low <400 RPM (running), High >8000 RPM
- **Failure modes**: Broken reluctor, wiring fault, ECU fault

### 3.8 CMP (Camshaft Position) Sensor
- **What it does**: Measures camshaft position for ignition timing
- **How it works**: Hall effect or magnetic — square wave signal
- **How to test**: Oscilloscope → square wave; scan tool → DTC P0340-P0349
- **Standard running data**: Sync with CKP (1:2 ratio)
- **Thresholds**: Signal missing = DTC P0340-P0349
- **Failure modes**: Wiring fault, ECU fault, broken reluctor

### 3.9 Knock Sensor
- **What it does**: Detects engine knock (detonation)
- **How it works**: Piezoelectric — voltage proportional to vibration
- **How to test**: Oscilloscope → AC signal; scan tool → DTC P0325-P0334
- **Standard running data**: 0-5V (AC), no knock = low voltage
- **Thresholds**: High >5V sustained = knock detected
- **Failure modes**: Broken sensor, wiring fault, ECU fault

### 3.10 Fuel Pressure Sensor
- **What it does**: Measures fuel rail pressure
- **How it works**: Piezoresistive — voltage proportional to pressure
- **How to test**: Scan tool → PID 01F0-01FF; compare to spec
- **Standard running data**: 300-500 kPa (idle), 3000-4000 kPa (WOT)
- **Thresholds**: Low <200 kPa (idle), High >5000 kPa (idle)
- **Failure modes**: Clogged filter, pump failure, wiring fault

### 3.11 EGR Valve Position Sensor
- **What it does**: Measures EGR valve position
- **How it works**: Potentiometer — voltage proportional to valve position
- **How to test**: Scan tool → PID 0140-014F; 0% = 0.5V, 100% = 4.5V
- **Standard running data**: 0.5V (closed), 4.5V (open), 1.0-4.0V (partial)
- **Thresholds**: Low <0.2V, High >4.8V
- **Failure modes**: Clogged valve, wiring fault, ECU fault

### 3.12 EVAP Canister Purge Valve
- **What it does**: Controls EVAP canister purge flow
- **How it works**: Solenoid — PWM duty cycle controls flow
- **How to test**: Scan tool → PID 0144-014B; duty cycle 0-100%
- **Standard running data**: 0% (closed), 50-80% (purge)
- **Thresholds**: Low <10%, High >95%
- **Failure modes**: Clogged valve, wiring fault, ECU fault

### 3.13 ABS Wheel Speed Sensors
- **What it does**: Measures wheel speed for ABS/ESC
- **How it works**: Reluctor + magnetic sensor — AC voltage pulses
- **How to test**: Oscilloscope → AC waveform; scan tool → RPM
- **Standard running data**: 0-200 km/h (vehicle speed)
- **Thresholds**: Low <5 km/h, High >250 km/h
- **Failure modes**: Broken reluctor, wiring fault, ECU fault

### 3.14 Steering Angle Sensor
- **What it does**: Measures steering wheel angle
- **How it works**: Potentiometer or Hall effect — voltage proportional to angle
- **How to test**: Scan tool → PID 0180-018F; 0° = center, ±900° range
- **Standard running data**: 0° (center), ±900° (max)
- **Thresholds**: Low < -900°, High > 900°
- **Failure modes**: Wiring fault, ECU fault, mechanical binding

### 3.15 Fuel Level Sensor
- **What it does**: Measures fuel tank level
- **How it works**: Float + potentiometer — resistance proportional to level
- **How to test**: Scan tool → PID 002F-003F; 0% = empty, 100% = full
- **Standard running data**: 0% (empty), 100% (full)
- **Thresholds**: Low <5%, High >100%
- **Failure modes**: Broken float, wiring fault, ECU fault

---

## 4. Scan Tool Categories

| Category | Brand | Features | Price Range |
|----------|-------|----------|-------------|
| OEM-Level | Launch X431 | Full OBD2, ECU coding, bi-directional | $500-$5,000 |
| OEM-Level | Bosch KTS 570/580 | Guided fault finding, waveforms | $1,000-$5,000 |
| OEM-Level | Snap-On MODIS | Advanced diagnostics, scope integration | $2,000-$10,000 |
| OEM-Level | Delphi DS150E | OEM-level diagnostics | $500-$2,000 |
| Budget/Prosumer | Autel MaxiCOM/MaxiSys | OBD2, ABS, SRS, EPB, oil reset | $200-$1,500 |
| Budget/Prosumer | BlueDriver | Bluetooth OBD2, iOS/Android | $50-$100 |
| Budget/Prosumer | Veepeak OBDCheck | Budget OBD2, real-time data | $20-$50 |
| Specialist | EDC17/MD1/DCM | Diesel ECU diagnostics | $500-$2,000 |
| Specialist | Hertz/Technician | Heavy duty truck diagnostics | $500-$2,000 |
| Specialist | i-HDS/HDS | Honda/Acura diagnostics | $500-$1,000 |
| Specialist | Techstream | Toyota/Lexus diagnostics | $500-$1,000 |

---

## 5. Protocols

| Protocol | Speed | Voltage | Pin | Description |
|----------|-------|---------|-----|-------------|
| ISO 9141-2 | 10.4 kbps | 12V | K-line | K-line startup, 5-baud init |
| ISO 14230-4 | 10.4 kbps | 12V | K-line | KWP2000, fast init |
| ISO 15765-4 | 500 kbps | 12V | CAN-H/CAN-L | CAN bus, OBD2-CAN |
| SAE J1850 PWM | 10.4 kbps | 5V | PWM | Ford, Chrysler |
| SAE J1850 VPW | 10.4 kbps | 12V | VPW | GM, early OBD2 |
| ISO 9141-2 (L-line) | 10.4 kbps | 12V | L-line | Asian vehicles |

---

## 6. Appendix — Non-Conversant Folk Reference

### What is OBD2?
On-Board Diagnostics II — standardized vehicle diagnostics system (US/EU). Plugs into OBD2 port (under dashboard). Reads DTCs, live data, performs tests.

### What is a DTC?
Diagnostic Trouble Code — 5-character code (e.g., P0171) indicating a fault. P=Powertrain, B=Body, C=Chassis, U=Network.

### What is a PID?
Parameter ID — live data value (e.g., engine RPM, coolant temp). Read via scan tool.

### What is CAN Bus?
Controller Area Network — vehicle communication network. Dual 500kΩ termination, 500k baud, J1939/OBD2-CAN.

### What is ECU?
Engine Control Unit — computer that manages engine. Flashable, codes stored in memory.

### What is DPF?
Diesel Particulate Filter — traps soot from exhaust. Regenerated by post-injection.

### What is EGR?
Exhaust Gas Recirculation — recirculates exhaust to reduce NOx. Controlled by EGR valve.

### What is VVT?
Variable Valve Timing — adjusts valve timing for efficiency. Controlled by VVT solenoid.

### What is MAF?
Mass Air Flow — measures air intake. Hot wire sensor. Standard: 2.5-4.0 g/s (idle).

### What is MAP?
Manifold Absolute Pressure — measures intake manifold pressure. Standard: 20-30 kPa (idle).

### What is TPS?
Throttle Position Sensor — measures throttle angle. Standard: 0.5V (closed), 4.5V (WOT).

### What is CKP?
Crankshaft Position Sensor — measures crankshaft RPM/position. Standard: 600-800 RPM (idle).

### What is CMP?
Camshaft Position Sensor — measures camshaft position. Syncs with CKP (1:2 ratio).

### What is O2?
Oxygen Sensor — measures exhaust O2. Standard: 0.1-0.9V (switching), 0.45V (steady).

### What is ECT?
Coolant Temperature Sensor — measures coolant temp. Standard: 85-95°C (operating).

### What is IAT?
Intake Air Temperature Sensor — measures intake air temp. Standard: 20-30°C (ambient).

### What is Knock Sensor?
Detects engine knock (detonation). Standard: 0-5V AC, no knock = low voltage.

### What is Fuel Pressure Sensor?
Measures fuel rail pressure. Standard: 300-500 kPa (idle), 3000-4000 kPa (WOT).

### What is EGR Valve?
Controls exhaust gas recirculation. Standard: 0.5V (closed), 4.5V (open).

### What is EVAP Canister?
Stores fuel vapors. Purge valve controls flow. Standard: 0% (closed), 50-80% (purge).

### What is ABS Wheel Speed Sensor?
Measures wheel speed for ABS/ESC. Standard: 0-200 km/h.

### What is Steering Angle Sensor?
Measures steering wheel angle. Standard: 0° (center), ±900° (max).

### What is Fuel Level Sensor?
Measures fuel tank level. Standard: 0% (empty), 100% (full).

---

## 7. Voice Q&A — Higher Paid Tier

### Standard Tier (2.5 credits)
- Basic DTC read
- Basic PID read
- Basic sensor test

### Pro Tier (5 credits)
- Bi-directional control
- ECU coding
- Advanced sensor test
- Threshold analysis
- Regression analysis

### Enterprise Tier (15 credits)
- Full ECU flash
- Adaptation reset
- Full sensor analysis
- AI-assisted diagnosis
- Repair workflow generation
- Historical data analysis
- Remote execution pipeline

### World-Class Tier (25 credits)
- Full ECU flash + adaptation
- AI-assisted fault prediction
- AI-assisted repair workflow
- Remote execution pipeline
- Voice Q&A (natural language)
- Predictive maintenance scheduling
- Integration with Hermes + OpenCode + Lazarus
- 24/7 monitoring + alert pipeline
- Auto-regression + trend analysis
- Custom threshold profiles
- Multi-vehicle fleet diagnostics
- Secure audit trail + token cost logging

### Voice Q&A Examples
- "What does P0171 mean?" → System Lean (Bank 1), check MAF, vacuum leaks, fuel pressure
- "How do I test MAF?" → Scan tool → PID P0101 → 2.5-4.0 g/s (idle) → <1.0 or >8.0 = fault
- "What is the standard idle RPM?" → 600-800 RPM (varies by vehicle)
- "What is the standard coolant temp?" → 85-95°C (operating)
- "What is the standard MAF reading?" → 2.5-4.0 g/s (idle)
- "What is the standard O2 voltage?" → 0.1-0.9V (switching), 0.45V (steady)
- "What is the standard fuel pressure?" → 300-500 kPa (idle), 3000-4000 kPa (WOT)
- "What is the standard IAT reading?" → 20-30°C (ambient), 40-60°C (operating)
- "What is the standard TPS voltage?" → 0.5V (closed), 4.5V (WOT)
- "What is the standard CKP RPM?" → 600-800 RPM (idle)
- "What is the standard ECT reading?" → 85-95°C (operating), 20-30°C (cold start)
- "What is the standard MAP reading?" → 20-30 kPa (idle), 80-100 kPa (WOT)
- "What is the standard fuel level?" → 0% (empty), 100% (full)
- "What is the standard ABS wheel speed?" → 0-200 km/h
- "What is the standard steering angle?" → 0° (center), ±900° (max)
- "What is the standard EGR valve position?" → 0.5V (closed), 4.5V (open)
- "What is the standard EVAP purge valve?" → 0% (closed), 50-80% (purge)
- "What is the standard knock sensor?" → 0-5V AC, no knock = low voltage
- "What is the standard fuel pressure sensor?" → 300-500 kPa (idle), 3000-4000 kPa (WOT)
- "What is the standard coolant temp sensor?" → 85-95°C (operating), 20-30°C (cold start)
- "What is the standard intake air temp sensor?" → 20-30°C (ambient), 40-60°C (operating)
- "What is the standard throttle position sensor?" → 0.5V (closed), 4.5V (WOT)
- "What is the standard crankshaft position sensor?" → 600-800 RPM (idle)
- "What is the standard camshaft position sensor?" → Sync with CKP (1:2 ratio)
- "What is the standard oxygen sensor?" → 0.1-0.9V (switching), 0.45V (steady)
- "What is the standard MAP sensor?" → 20-30 kPa (idle), 80-100 kPa (WOT)
- "What is the standard fuel level sensor?" → 0% (empty), 100% (full)
- "What is the standard ABS wheel speed sensor?" → 0-200 km/h
- "What is the standard steering angle sensor?" → 0° (center), ±900° (max)
- "What is the standard EGR valve position sensor?" → 0.5V (closed), 4.5V (open)
- "What is the standard EVAP canister purge valve?" → 0% (closed), 50-80% (purge)
- "What is the standard knock sensor?" → 0-5V AC, no knock = low voltage
- "What is the standard fuel pressure sensor?" → 300-500 kPa (idle), 3000-4000 kPa (WOT)