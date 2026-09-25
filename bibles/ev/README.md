# EV Bible — World-Class Diagnostic & Integration

## Vehicle Categories
- BEV (Battery Electric): Tesla, BYD, Rivian, Lucid
- PHEV (Plug-in Hybrid): Toyota, BMW i3, Volvo
- HEV (Hybrid): Toyota Prius, Honda Insight
- FCEV (Fuel Cell): Toyota Mirai, Hyundai Nexo

## Battery Architecture
| Component | Spec | Protocol |
|-----------|------|----------|
| HV Battery (BEV) | 400V-800V Li-ion | CAN |
| 12V Aux Battery | 12V AGM | OBD2 |
| BMS (Battery Mgmt) | Cell-level monitoring | CAN |
| Inverter | 3-phase AC motor drive | CAN |
| DC-DC Converter | HV→12V isolation | CAN |
| Motor Controller | PWM drive, regen | CAN |

## Safety Protocols
- **HV Disconnect**: Service plug removal before any work
- **Isolation Check**: >500MΩ resistance HV→chassis
- **Personal Protection**: CAT III 1000V gloves + face shield
- **Ground Fault**: 30mA max leakage (IEC 61851)
- **Lockout/Tagout**: Physical disconnect before ECU access

## Diagnostic Stack
```
EV-Specific PIDs:
- SOC (State of Charge): 0-100%, ±2% accuracy
- SOH (State of Health): % of original capacity
- Cell Voltage: 2.5V-4.2V per cell (Li-ion)
- Temperature: -30°C to +60°C (operating), +85°C (max)
- Insulation Resistance: MΩ value (HV→chassis)
- Motor Speed: RPM (0-18000 for BEV)
- Regenerative Braking: kW value
```

## Charge Protocols
- **Type 1 (J1772)**: AC charging, 1-phase/3-phase, 240V
- **Type 2 (Mennekes)**: EU AC/DC, 3-phase, 230V/400V
- **CCS (Combined Charging)**: DC fast charge, 350kW max
- **Tesla Proprietary**: 250kW supercharger (v3)
- **CHAdeMO**: DC, 50kW typical (older BEV)

## Remote Monitoring (Groq Integration)
```
Sensor Feed → Analysis Engine → Alert Pipeline
```
- Battery degradation prediction (machine learning)
- Range optimization (traffic, weather, route)
- Charge time estimation (station capacity, SOC, battery temp)
- Predictive maintenance (motor bearing wear, inverter efficiency)

## Integration Points
- **Hermes**: EV-specific model picker (Tesla/BYD/Rivian adapters)
- **OpenCode**: Remote charge management (start/stop, scheduling)
- **Lazarus**: Vault stores charge profiles, battery health history
- **Console**: HV isolation status monitoring before any remote work

## Pay-Grade: Enterprise Only
- Basic SOC read: Standard (2.5 credits)
- Full BMS analysis + cell-level data: Enterprise (15 credits)
- Remote charge optimization + predictive: Enterprise+ (25 credits)
- Full ECU flash (inverter, BMS, motor controller): World-Class (50 credits + signed authorization)