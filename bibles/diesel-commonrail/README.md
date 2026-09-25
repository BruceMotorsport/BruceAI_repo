# Diesel Common Rail Bible — World-Class

## Architecture
```
Fuel Tank → Lift Pump → HP Pump → Common Rail → Injectors → Cylinder
                ↑                ↑                ↑
         Fuel Filter        Pressure Sensor   Solenoid/ Piezo
```

## Key Components
| Component | Function | Spec |
|-----------|----------|------|
| HP Pump (CP3/CP4) | High-pressure generation | 1,800-2,500 bar |
| Common Rail | Fuel reservoir | 1,200-2,500 bar |
| Injectors | Metered fuel delivery | 5-7 injections per cycle |
| Rail Pressure Sensor | Feedback control | ±2% accuracy |
| EDC17 ECU | Engine management | Bosch, 32-bit |

## Pressure Ranges
- Idle: 300-500 bar
- Full load: 1,800-2,500 bar (CP3)
- Maximum: 2,700 bar (CP4.4)
- Cold start: 400-600 bar (higher for cold)

## Injection Strategies
- **Pilot Injection**: Pre-injection, 0.2-0.5ms duration, reduces noise
- **Main Injection**: Primary combustion, 2-10ms duration
- **Post Injection**: After-burn, 0.3-1.0ms, regen control
- **After-Injection**: Late, 0.5-1.5ms, DPF regen

## DTC Dictionary (EDC17)
| Code | Description | Cause |
|------|-------------|-------|
| P0191 | Rail pressure sensor A | Wiring, sensor failure |
| P0193 | Rail pressure sensor A (low) | Short to ground |
| P0194 | Rail pressure sensor A (high) | Short to 12V |
| P0087 | Rail pressure too low | Fuel filter, pump, leak |
| P0088 | Rail pressure too high | Overpressure, sensor |
| P0093 | Fuel system leak detected | Leak detection pump |
| P0101 | MAF circuit range/performance | Sensor, wiring, ECU |
| P0201-P0208 | Injector circuit (cyl 1-8) | Wiring, injector, ECU |

## Common Rail Service Procedures
1. **Fuel Filter**: Replace every 20,000-30,000 miles
2. **Fuel Water Separator**: Drain every 10,000 miles
3. **Rail Pressure Test**: Measure at idle, load, cranking
4. **Leak-Off Test**: Measure return rate per injector
5. **Injection Timing**: Verify via scan tool + crankshaft sensor

## Groq Integration
```
Rail Pressure Analysis:
- Current: {value} bar
- Target: {value} bar
- Deviation: {value} bar
- Diagnosis: {result}
- Repair: {steps}
```

## Pay-Grade
- Basic DTC read: Standard (2.5 credits)
- Rail pressure analysis + injector test: Pro (5 credits)
- Full EDC17 flash + adaptation: Enterprise (15 credits)
- World-Class: AI-assisted diagnosis + repair workflow (25 credits)