# Automatic Transmission Bible — World-Class

## Quick Reference Search Bar
```
Search: [Type/Sensor/Actuator/Control Unit/DTC] → jump to section
```

### Index
1. Transmission Types
2. Hydraulic Systems (ATF, Pumps, Valves)
3. Sensors — What It Does / How It Works / How to Test / Standard Data / Thresholds
4. Actuators — Solenoids, EPC, Mechanical Components
5. Control Units — TCM (Transmission Control Module)
6. Theory of Operation — Planetary Gears, Shift Scheduling, Hydraulic Pressure
7. Diagnostic — DTC Dictionary, PID, Scan Tool Setup
8. Service Procedures — Fluid Flush, Adaptive Learning, Shift Adaptation Reset
9. Appendix — Non-Conversant Folk Reference
10. Voice Q&A — Higher Paid Tier

---

## 1. Transmission Types

### 1.1 Automatic vs. Manual vs. CVT
| Type | Control | Efficiency | Pros | Cons |
|------|---------|------------|------|------|
| Traditional Automatic (Torque Converter) | Hydraulic/TCM | 85-90% | Smooth shifting, robust | Heat loss, fuel penalty |
| Dual Clutch (DCT) | Electronic, hydraulic pressure | 95-98% | Fast shifts, high efficiency | Complex, high cost |
| Continuously Variable (CVT) | Electronic, pulley ratio | 92-95% | Optimal engine operation | Belt wear, unusual noise |

### 1.2 4-Speed, 6-Speed, 8-Speed, 10-Speed
| Speed Count | Use Case | Efficiency Gain | Shift Characteristics |
|-------------|----------|------------------|----------------------|
| 4-Speed | Heavy trucks, older cars | Baseline | Wide shift spread |
| 6-Speed | Modern sedans, SUVs | +5-8% | Close ratios, sporty |
| 8-Speed | Performance vehicles | +8-12% | Racing performance, comfort |
| 10-Speed | SUVs, trucks | +12-15% | Wide ratio spread, efficiency |

### 1.3 RWD vs. FWD vs. AWD
| Layout | Power Delivery | Efficiency | Common Vehicles |
|--------|----------------|------------|-----------------|
| RWD | Longitudinal torque | Best cooling, weight | BMW M, Mustang |
| FWD | Transaxle, lighter | Packaging efficiency | Camry, Civic |
| AWD | Multi-mode, all-wheel | Comfort + capability | Wrangler, RAV4 AWD |

### 1.4 Electrified Integration
| Powertrain | Transmission Adaptation | Service Note |
|------------|----------------------|-------------|
| HEV | Reduced size, motor-assisted | Monitor regenerative shift |
| PHEV | Larger motor, e-CVT | Service regenerative control logic |
| BEV | Single-speed, no traditional | No ATF, monitor inverter cooling |

---

## 2. Hydraulic Systems (ATF Circuit)

### 2.1 ATF (Automatic Transmission Fluid)
```
Composition: 40% base oil + 60% additive package
Viscosity: 350-650 SUS at 100°F (API GL-4/GL-5)
Service Interval: Every 60,000-100,000 miles |
```

### 2.2 Hydraulic Pump
| Component | Specification | Purpose |
|-----------|----------------|---------|
| Gear Pump | 4-6 pages @ 1,000-2,000 psi | Oil circulation |
| Pressure Control | 500-2,000 psi (variable) | Shift control |
| Flow Control | 2-8 L/min (variable) | Adaptive shifts |

### 2.3 Valve Body & Solenoids
| Solenoid | Voltage | Current | Function |
|----------|---------|---------|----------|
| Shift Solenoid | 12V | 2-5A | Control shift timing |
| Lock-Up Solenoid | 12V | 1-3A | Engage converter lock-up |
| Line Pressure Solenoid | 12V | 2-4A | Control line pressure |

### 2.4 Torque Converter
| Parameter | Specification | Tolerance |
|------------|----------------|----------|
| Clutch Capacity | 2-4x engine torque | ±10% |
| Lock-Up Speed | 2,500-3,500 RPM | ±200 RPM |
| Efficiency (locked) | 95-98% | ±2% |
| Efficiency (slip) | 80-85% | ±3% |

### 2.5 Control Valve Assembly
| Valve | Actuation | Control |
|-------|-----------|---------|
| Main Pressure Valve | Solenoid | Line pressure |
| Shift Valve | Hydraulic | Shift scheduling |
| Stalling Valve | Line pressure | Prevent stall |
| Binding Valve | Spring | Prevent binding |

---

## 3. Sensors — What It Does / How It Works / How to Test / Standard Data / Thresholds

### 3.1 Vehicle Speed Sensor (VSS)
|- **What it does**: Measures wheel speed to calculate gear selection |
|- **How it works**: Hall effect or magnetoresistive — pulses per revolution |
|- **How to test**: Scan tool → PID “Vehicle Speed”; compare to speedometer |
|- **Standard running data**: 0-150 km/h (varies by vehicle) |
|- **Thresholds**: Low <1 km/h, High >180 km/h |
|- **Failure modes**: Broken sensor tooth, wiring fault, ECU fault |

### 3.2 Throttle Position Sensor (TPS)
|- **What it does**: Measures accelerator pedal position for shift scheduling |
|- **How it works**: Potentiometer — voltage varies with pedal angle |
|- **How to test**: Scan tool → PID “TPS”; 0° = 0.5V, 100° = 4.5V |
|- **Standard running data**: 0-12 V (0° = 0.5V, 100° = 4.5V) |
|- **Thresholds**: Low <0.2V, High >4.8V |
|- **Failure modes**: Broken potentiometer, voltage drift, ECU fault |

### 3.3 Brake Switch (BRK)
|- **What it does**: Signal to cancel shift into Drive when brake applied |
|- **How it works**: Normally open, closes when pedal pressed |
|- **How to test**: Scan tool → PID “Brake Switch”; 0V = released, 12V = pressed |
|- **Standard running data**: 0V (released), 12V (pressed) |
|- **Thresholds**: Low <0.5V, High >10V |
|- **Failure modes**: Open circuit, short to ground, ECU fault |

### 3.4 Engine Speed Sensor (ESS)
|- **What it does**: Provides RPM for shift schedule and torque limits |
|- **How it works**: Magnetic pickup or Hall effect — AC voltage pulses |
|- **How to test**: Oscilloscope → waveform; scan tool → RPM |
|- **Standard running data**: 600-7,000 RPM (idle to redline) |
|- **Thresholds**: Low <400 RPM (running), High >8,000 RPM |
|- **Failure modes**: Broken reluctor ring, wiring fault, ECU fault |

### 3.5 Crankshaft Position Sensor (CKP)
|- **What it does**: Timing reference for ECU, synchronized with ESS |
|- **How it works**: Optical or magnetic — square wave signal |
|- **How to test**: Oscilloscope → square wave; scan tool → DTC P0335-P0349 |
|- **Standard running data**: Sync with ESS (1:1) |
|- **Thresholds**: Signal missing = DTC P0340-P0349 |
|- **Failure modes**: Wiring fault, ECU fault, broken reluctor |

### 3.6 ATF Temperature Sensor (ATF Temp)
|- **What it does**: Measures transmission fluid temperature for cooling control |
|- **How it works**: Thermistor — resistance decreases with temperature |
|- **How to test**: Scan tool → PID “ATF Temp”; compare to infrared |
|- **Standard running data**: 80-120°C (operating), 150-180°C (max) |
|- **Thresholds**: Low <50°C, High >250°C |
|- **Failure modes**: Broken sensor, wiring short, ECU fault |

### 3.7 Line Pressure Sensor (Line Press)
|- **What it does**: Measures main hydraulic pressure for shift quality |
|- **How it works**: Piezoresistive — voltage proportional to pressure |
|- **How to test**: Scan tool → PID “Line Pressure”; compare to pressure gauge |
|- **Standard running data**: 300-1,200 psi (idling to WOT) |
|- **Thresholds**: Low <200 psi, High >2,000 psi |
|- **Failure modes**: Clogged filter, pump failure, wiring fault |

### 3.8 Shift Solenoid Current Sense (Shift Sol)
|- **What it does**: Verifies solenoid current for shift quality |
|- **How it works**: Current sensing resistor in solenoid circuit |
|- **How to test**: Scan tool → PID “Shift Sol Current”; compare to spec |
|- **Standard running data**: 1-5A (varies by solenoid) |
|- **Thresholds**: Low <0.5A, High >8A |
|- **Failure modes**: Solenoid short, wiring fault, ECU fault |

### 3.9 Adaptive Learning Sensor (Adapt)
|- **What it does**: Learns shift characteristics based on driving habits |
|- **How it works**: TCM stores shift timing maps |
|- **How to test**: Scan tool → Adaptive Data; observe shift adaptation |
|- **Standard running data**: Stores 0-255 values per shift adaptation |
|- **Thresholds**: High >200 (detuned) |
|- **Failure modes**: TCM corruption, memory failure |

### 3.10 Neutral Start Switch (NSS)
|- **What it does**: Safety interlock — prevents starting in Drive |
|- **How it works**: Normally open, closes when gear in Neutral/Park |
|- **How to test**: Switch to Neutral/Park → voltage 12V; in Drive → 0V |
|- **Standard running data**: 0V (invalid), 12V (valid) |
|- **Thresholds**: Low <0.5V, High >10V |
|- **Failure modes**: Open switch, short to ground, ECU fault |

### 3.11 Transmission Range Switch (TRS)
|- **What it does**: Multiplexed gear position signal |
|- **How it works**: PWM or analog — gear position identification |
|- **How to test**: Scan tool → PID “Gear Position”; mechanical verification |
|- **Standard running data**: 0 (Park), 1 (Reverse), 2 (Neutral), 3 (Drive) |
|- **Thresholds**: Each gear 0-12V range |
|- **Failure modes**: Broken switch, wiring fault, ECU fault |

---

## 4. Actuators — Solenoids, EPC, Mechanical Components

### 4.1 Shift Solenoid
|- **What it does**: Controls fluid flow to shift valves |
|- **How it works**: Electromagnetic — solenoid opens/closes hydraulic path |
|- **How to test**: Apply 12V → audible click; scan tool → PID current |
|- **Standard running data**: 12V @ 2-5A |
|- **Failure modes**: Burned coil, stuck open/closed, solenoid shaft |

### 4.2 Lock-Up Solenoid
|- **What it does**: Engages torque converter lock-up for efficiency |
|- **How it works**: Electromagnetic — releases spring-loaded piston |
|- **How to test**: Apply 12V → listen for engagement click; scan tool → lock-up status |
|- **Standard running data**: Engages >2,500 RPM, disengages <1,500 RPM |
|- **Thresholds**: Slip >5% (locked), Stall <500 RPM |
|- **Failure modes**: Stuck open/closed, hydraulic leak, converter clutch |

### 4.3 Line Pressure Control Valve
|- **What it does**: Regulates main hydraulic line pressure |
|- **How it works**: Hydraulic spool valve actuated by line pressure solenoid |
|- **How to test**: Pressure gauge test; scan tool → line pressure PID |
|- **Standard running data**: 300-1,200 psi (variable) |
|- **Failure modes**: Spool stuck, spring failure, valve body wear |

### 4.4 EPC (Electronic Pressure Control)
|- **What it does**: Digital control of line pressure using PWM |
|- **How it works**: PWM signal to solenoid → proportional pressure |
|- **How to test**: Scan tool → EPC current; apply throttle, measure pressure |
|- **Standard running data**: 0-100% duty cycle |
|- **Thresholds**: Low <10% duty, High >90% duty |
|- **Failure modes**: PWM failure, solenoid open, ECU fault |

### 4.5 Mechanical Shift Linkage
|- **What it does**: Physical connection between shift cable and valve body |
|- **How it works**: Lever arm and pivot system |
|- **How to test**: Manual shift → mechanical play; scan tool → gear position |
|- **Standard running data**: 0-2mm play in linkage |
|- **Thresholds**: Excessive play >5mm, binding |
|- **Failure modes**: Wear, broken pivot, hydraulic binding |

---

## 5. Control Units — TCM (Transmission Control Module)

### 5.1 TCM Architecture
| Component | Function | Redundancy |
|-----------|----------|-----------|
| Processor | Shift scheduling, adaptive learning | Dual-core |
| Memory | Shift maps, adaptive data | Flash + RAM |
| Sensors | VSS, TPS, ESS, ATF Temp, etc. | Redundant channels |
| Outputs | Solenoid control, CAN bus | Two independent circuits |
| Communication | CAN, OBD2, LIN | Multi-protocol |

### 5.2 Shift Scheduling Algorithm
```
IF Vehicle Speed < 30 km/h AND Throttle Position > 50% AND ATF Temp > 80°C
  SET Shift to Drive IMMEDIATELY
ELSE IF Vehicle Speed > 100 km/h AND Throttle Position < 20%
  SET Shift to Neutral for engine braking
ELSE IF Engine Torque > 300 Nm AND ATF Pressure < 500 psi
  ADJUST Shift schedule for torque management
END IF
```

### 5.3 Adaptive Learning Logic
|- **Shift Adaptation**: Adjusts shift timing based on driver behavior |
|- **Torque Management**: Limits shift harshness based on vehicle load |
|- **Temperature Compensation**: Adjusts pressure based on ATF temperature |
|- **Failure Detection**: Monitors sensor currents, solenoid voltages |

### 5.4 CAN Bus Integration
|- **PCM Integration**: Syncs engine RPM and throttle for shift scheduling |
|- **ABS Integration**: Synchronizes shift control with braking |
|- **Cruise Control**: Adjusts shift points for fuel economy |

---

## 6. Theory of Operation — Planetary Gears, Shift Scheduling, Hydraulic Pressure

### 6.1 Planetary Gear Set
```
{                 {  Clutch B       {                    {
R ← Sun → Planet Carrier → Ring → Planet Carrier ← Sun ← R
                 }  (Fixed)       }  (Variable)           }
```
- **Gear Ratios**: 
  - Park/Neutral: Sun fixed, carrier output = 0
  - Reverse: Carrier fixed, output = -3.5:1
  - Drive Low: Ring fixed, output = 2.5:1
  - Drive High: Sun fixed, output = 1.5:1

### 6.2 Hydraulic Pressure Control
|- **Line Pressure**: Generated by gear pump, controlled by line pressure solenoid |
|- **Shift Pressure**: Higher than line pressure, controls valve timing |
|- **Pressure Ratios**: 1:4 (line:shift) for fine control |

### 6.3 Shift Scheduling Algorithm
|- **Speed Thresholds**: 0-30 km/h (long shift), 30-80 km/h (normal), >80 km/h (sport) |
|- **Torque Management**: Low torque = aggressive shifts, high torque = delayed shifts |
|- **Throttle Mapping**: 0-50% (light), 50-80% (moderate), >80% (heavy) |

### 6.4 Electronic Control System
|- **TCM Inputs**: VSS, ESS, TPS, ATF Temp, brake switch, neutral start |
|- **TCM Outputs**: Shift solenoids, lock-up solenoid, line pressure control |
|- **Feedback Loops**: Real-time pressure monitoring, adaptive learning |

---

## 7. Diagnostic — DTC Dictionary, PID, Scan Tool Setup

### 7.1 DTC Dictionary (P0400-P0499)
|| Code | Description | Cause |
||------|-------------|-------|
|| P0740 | Torque Converter Clutch Circuit | Solenoid, wiring, converter |
|| P0741 | Torque Converter Clutch Circuit Performance | Oil, slippage |
|| P0742 | Torque Converter Clutch Circuit Inability to Hold | Pressure, mechanical |
|| P0780 | Shift Malfunction |
|| P0781 | Shift Time Out Of Range | Shift solenoid |
|| P0782 | Over Select Reduction |
|| P0783 | Integration Time Range Performance |
|| P0790 | Incorrect Gear Ratio |
|| P0791 | No 4th Gear |
|| P0792 | No 5th Gear |
|| P0793 | No 6th Gear |
|| P0794 | No 7th Gear |
|| P0795 | No 8th Gear |
|| P0796 | No 9th Gear |
|| P0798 | Multiple Gear 2 Failure |

### 7.2 PID Readings (CAN vs. OBD2)
|| PID | Description | Typical Value | Unit |
||-----|-------------|----------------|------|
|| Vehicle Speed | Wheel speed | 0-150 | km/h |
|| Engine RPM | Crankshaft speed | 600-7,000 | RPM |
|| Throttle Position | Pedal angle | 0-12 | V |
|| ATF Temperature | Fluid temp | 80-120 | °C |
|| Line Pressure | Main pressure | 300-1,200 | psi |
|| Shift Solenoid Current | Solenoid current | 1-5 | A |
|| Adaptive Data | Shift adaptation | 0-255 | (code) |
|| Gear Position | Selected gear | 0-3 | (code) |

### 7.3 Scan Tool Setup
|- **CAN Bus Speed**: 500 kbps (standard) |
|- **OBD2 Port**: 16-pin J1962 |
|- **Protocol Priority**: CAN > ISO9141 > KWP |
|- **Session**: Bidirectional control mode for solenoid tests |

### 7.4 Diagnostic Procedures
|- **Visual Inspection**: Check for fluid leaks, damaged hoses |
|- **Mechanical Inspection**: Verify linkage play, worn components |
|- **Electrical Testing**: Solenoid continuity, sensor voltages |
|- **Hydraulic Testing**: Pressure gauges, flow tests |

---

## 8. Service Procedures — Fluid Flush, Adaptive Learning, Shift Adaptation Reset

### 8.1 Fluid Flush Procedure
1. **Verify Fluid Level**: Warm engine, check dipstick |
2. **Remove Drain Plug**: Drain ATF |
3. **Flush System**: Fill with flush fluid, run engine |
4. **Replace Filter**: New transmission filter |
5. **Refill**: Manufacturer-specified ATF |
6. **Run Adaptive Learning**: Normal driving conditions |

### 8.2 Shift Adaptation Reset
|- **Procedure**: Start engine, park, selector in Park |
|- **Scanner**: Clear adaptation data |
|- **Relearn**: Normal driving for 2-3 days |
|- **Verify**: Smooth shifts after adaptation |

### 8.3 Solenoid Testing
|- **Solenoid Continuity**: 12V @ 2-5A |
|- **Solenoid Resistance**: 10-30 ohms |
|- **Solenoid Operation**: Audible click on 12V |

### 8.4 Mechanical Service
|- **Transmission Pan**: Check for metal shavings |
|- **Torque Specs**: Re-torque mounting bolts |
|- **Seal Replacement**: Gasket, O-rings |

---

## 9. Appendix — Non-Conversant Folk Reference

### 9.1 What Is ATF?
Automatic Transmission Fluid — hydraulic fluid that lubricates, cools, and creates pressure for gear shifts.

### 9.2 What Is a TCM?
Transmission Control Module — the computer that controls shifts, torque converter lock-up, and adaptive learning.

### 9.3 What Is a Solenoid?
Electromagnetic valve that controls fluid flow for shifts and lock-up.

### 9.4 What Is Lock-Up?
Torque converter lock-up — engages direct drive between engine and transmission for efficiency.

### 9.5 What Is Adaptive Learning?
Automatic adjustment of shift timing based on driver behavior and conditions.

### 9.6 What Is Planetary Gear?
Gear system using sun, planet carrier, and ring gears for multiple gear ratios.

### 9.7 What Is Hydraulic Pressure?
Fluid pressure generated by pump, used to control shift timing and strength.

### 9.8 What Is EPC?
Electronic Pressure Control — digital regulation of line pressure using PWM.

### 9.9 What Is DTC?
Diagnostic Trouble Code — standardized fault code (e.g., P0740 for TCC circuit).

### 9.10 What Is PID?
Parameter ID — live data value (e.g., Vehicle Speed, Engine RPM).

### 9.11 What Is CAN Bus?
Controller Area Network — vehicle communication network (500 kbps standard).

### 9.12 What Is OBD2?
On-Board Diagnostics II — standardized diagnostic port (16-pin J1962).

---

## 10. Voice Q&A — Higher Paid Tier

### Standard Tier (2.5 credits)
|- Basic DTC read |
|- Basic PID read |
|- Basic sensor test |

### Pro Tier (5 credits)
|- Bi-directional control |
|- Solenoid test |
|- Line pressure check |
- Adaptive learning reset

### Enterprise Tier (15 credits)
|- Full TCM flash |
|- Shift schedule analysis |
|- Mechanical inspection |
|- Fluid flush procedure |
|- Adaptive learning relearn |
- Solenoid replacement

### World-Class Tier (25 credits)
|- Full TCM flash + adaptation |
|- AI-assisted fault prediction |
|- AI-assisted repair workflow |
|- Remote execution pipeline |
|- Voice Q&A (natural language) |
|- Predictive maintenance scheduling |
|- Integration with Hermes + OpenCode + Lazarus |
|- 24/7 monitoring + alert pipeline |
|- Auto-regression + trend analysis |
|- Custom threshold profiles |
|- Multi-vehicle fleet diagnostics |
|- Secure audit trail + token cost logging |

### Voice Q&A Examples
|- "What does P0740 mean?" → TCC circuit fault; check solenoid, wiring, converter |
|- "How do I test a shift solenoid?" → Scan tool → Shift Sol Current → apply 12V |
|- "What is the standard line pressure?" → 300-1,200 psi (variable) |
|- "What is the standard ATF temperature?" → 80-120°C (operating) |
|- "What is the standard engine RPM?" → 600-7,000 RPM |
|- "What does the TCM do?" → Controls shifts, lock-up, adaptive learning |
|- "What is EPC?" → Electronic Pressure Control using PWM |
|- "How do I reset shift adaptation?" → Scanner clear, normal driving 2-3 days |
|- "What is lock-up?" → Torque converter direct drive for efficiency |
|- "What is a planetary gear?" → Sun/planet/ring gear set for multiple ratios |
|- "How do I check ATF level?" → Warm engine, dipstick 80-120°C |
|- "What causes hard shifts?" → Solenoid failure, low pressure, worn components |
|- "How often change ATF?" → 60,000-100,000 miles |
|- "What is adaptive learning?" → Shift timing based on driver behavior |
|- "What is a VSS?" → Vehicle Speed Sensor, wheel speed pulses |
|- "What is TPS?" → Throttle Position Sensor, pedal angle |
|- "What is ATF Temp?" → Transmission fluid temperature |
|- "What is line pressure?" → Main hydraulic pressure |
|- "What is shift adaptation?" → Stored shift timing values |
|- "What is neutral start?" → Safety interlock prevents starting in Drive |
|- "What is shift solenoid?" → Electromotive valve controls fluid flow |
|- "What is lock-up solenoid?" → Engages torque converter direct drive |
- (Continue for all sensors/actuators in sections 3 and 4)
