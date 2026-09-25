# Mechatronics Full Course Bible — World-Class

## Quick Reference Search Bar
```
Search: [Sensors/Actuators/Control Units/Theory/Design/Diagnostic/PLC] → jump to section
```

### Index
1. What Is Mechatronics?
2. Hydraulic Systems — Full Course
3. Pneumatic Systems — Full Course
4. Electric/Electronic Systems
5. Sensors — Types, Functions, Testing
6. Actuators — Hydraulic, Pneumatic, Electric
7. Control Systems — PLC, PID, Logic
8. Theory of Operation — Dynamics, Feedback, Stability
9. Design Principles — Safety, Reliability, Maintainability
10. Diagnostic Procedures — Troubleshooting, Fault Trees
11. Integration — CAN Bus, Ethernet, Fieldbus
12. Voice Q&A — Higher Paid Tier

---

## 1. What Is Mechatronics?

Mechatronics = **Mechanical + Electronics + Computer + Control**

| Discipline | Function | Tools |
|------------|----------|-------|
| Mechanical | Motion, force, energy | CAD, FEA, kinematics |
| Electronics | Sensing, amplifying | PCB, schematics |
| Computer | Data processing | PLC, PC, Embedded |
| Control | Dynamic response | PID, ladder, SCL |

---

## 2. Hydraulic Systems — Full Course

See `hydraulic-systems/README.md` for:
- ISO VG 15-68 fluid properties
- Gear, piston, vane pumps (200-500 bar)
- Single/double cylinders (5-50 kN)
- 4/3, 3/2 directional valves
- Pressure sensors, flow testing
- Pascal's law, Bernoulli equation
- Leak detection, pressure decay
- Fluid analysis, filter service

---

## 3. Pneumatic Systems — Full Course

See `pneumatic-systems/README.md` for:
- Compressed air classes (ISO 8573)
- Piston, screw, scroll compressors
- Single/double cylinders (10-50 kN)
- 4/3, 3/2, 5/2 valves
- FRL units, air dryers
- Pressure sensors, position sensors
- Boyle's law, ideal gas law
- Leak detection, ultrasonic testing

---

## 4. Electric/Electronic Systems

### 4.1 Motors
| Type | Voltage | Current | Speed | Torque | Use |
|------|---------|---------|-------|--------|-----|
| Induction | 230/400V | 1-10A | 1,500-3,000 RPM | 5-50 Nm | Pumps |
| Servo | 24-70V | 1-20A | 0-10,000 RPM | 0.1-100 Nm | Precision |
| Stepper | 12-48V | 0.5-5A | 0-2,000 RPM | 0.01-10 Nm | Positioning |
| DC | 12-24V | 1-20A | 0-10,000 RPM | 0.1-100 Nm | Tools |

### 4.2 Drives
| Type | Control | Feedback |
|------|---------|----------|
| VFD | Frequency | Encoder |
| Soft Starter | Voltage Ramp | Current |
| Vector Control | Field-oriented | Qu encoder |

### 4.3 Power Electronics
|- **Inverter**: DC → AC (VFD) |
|- **Converter**: AC → DC ( rectifier) |
|- **Regulator**: Voltage stability |
|- **Contactors**: High-power switching |
|- **Relays**: Low-power switching |

---

## 5. Sensors — Types, Functions, Testing

### 5.1 Position Sensors
| Type | Range | Accuracy | Output |
|------|-------|----------|--------|
| Potentiometer | ±360° | ±0.5% | 0-5V |
| LVDT | ±50 mm | ±0.1% | 0-5V |
| Encoder | 0-360° | ±0.01° | Pulse |
| Hall Effect | Proximity | ±0.5 mm | Digital |

### 5.2 Force/Torque Sensors
| Parameter | Specification | Typical |
|-----------|---------------|---------|
| Capacity | Nm | 0.1-500 |
| Accuracy | % | ±0.5-2.0% |
| Bandwidth | Hz | 0-1,000 |
| Output | mV/V | 2-10 |

### 5.3 Proximity Sensors (Inductive)
|- **What it does**: Detects metallic objects without contact |
|- **How it works**: Eddy current change in coil resonant frequency |
|- **How to test**: Multimeter → 24V→output; verify switching distance |
|- **Standard data**: 24V DC, PNP/NPN, M12 connector |
|- **Thresholds**: Distance 2-30 mm, response time <10 ms |
|- **Failure modes**: Contamination, coil burn, wiring fault |

### 5.4 Pressure Sensors (Digital)
|- **What it does**: Measures electrical/electronic system pressure |
|- **How it works**: MEMS diaphragm, strain gauge amplification |
|- **How to test**: Multimeter → compare to reference gauge |
|- **Standard data**: 0-24V, 4-20 mA, 0-5V, 0-10V |
|- **Thresholds**: Accuracy ±0.25% FS |
|- **Failure modes**: Overload, spike damage, calibration drift |

---

## 6. Actuators — Controlled Movement

### 6.1 Electro-Hydraulic
| Parameter | Specification |
|-----------|----------------|
| Voltage | 24V DC |
| Current | 2-10A |
| Speed | 50-500 mm/s |
| Position | ±0.1 mm |
| Feedback | Linear variable |

### 6.2 Electro-Pneumatic
| Parameter | Specification |
|-----------|----------------|
| Voltage | 24V DC |
| Pressure | 6-10 bar |
| Speed | 50-500 mm/s |
| Position | ±0.5 mm |
| Feedback | Proximity sensor |

### 6.3 Servomotor
|- **What it does**: Precise position/speed/torque control |
|- **How it works**: Encoder feedback → PID loop → drive |
|- **How to test**: Oscilloscope → sine wave tracking test |
|- **Standard data**: 0-10,000 RPM, 0.01° resolution |
|- **Thresholds**: Overshoot <5%, settling <100 ms |
|- **Failure modes**: Encoder fault, motor winding, drive fault |

---

## 7. Control Systems

### 7.1 PID Controller
```
e(t) = SP - PV
P = Kp × e(t)
I = Ki × ∫e(t)dt
D = Kd × de(t)/dt
Output = P + I + D
```

| Parameter | Typical | Tolerance |
|-----------|---------|-----------|
| Kp | 1-100 | ±20% |
| Ki | 0.1-10 | ±20% |
| Kd | 0.01-1 | ±20% |

### 7.2 PLC Scan Cycle
1. **Input Scan**: Read physical inputs
2. **Program Scan**: Execute ladder/logic
3. **Output Scan**: Update outputs
4. **Communication**: Send/receive data

### 7.3 Ladder Logic Basics
```
|----[ ]----( )----|     // Contact + Coil
|----[ ]----( )----|     // Normally open
|----[ ]----( )----|     // Normally closed
|----[ / ]----( )----|    // NOT gate
|----[ & ]----( )----|    // AND gate
|----[ | ]----( )----|    // OR gate
```

---

## 8. Theory of Operation

### 8.1 Feedback Control Loop
```
Reference → Summing Junction → Controller → Actuator → Plant → Sensor → Feedback
```

### 8.2 Stability Criteria
|- **Gain Margin**: >6 dB |
|- **Phase Margin**: >45° |
|- **Bandwidth**: 0.5-10× crossover frequency |

### 8.3 Response Characteristics
| Parameter | Specification |
|-----------|---------------|
| Steady-State Error | <2% |
| Rise Time | <10% of setpoint |
| Overshoot | <10% |
| Settling Time | <4 time constants |

---

## 9. Design Principles

### 9.1 Safety Integrity (SIL)
| SIL | Risk Reduction | Required |
|-----|----------------|----------|
| SIL 1 | 10-100 | Basic diagnostics |
| SIL 2 | 100-1000 | Redundant sensors |
| SIL 3 | 1000-10,000 | Dual channel, self-test |

### 9.2 Reliability
|- **MTBF**: 10,000-100,000 hours |
|- **Availability**: 95-99.9% |
|- **Redundancy**: 1oo2, 2oo2, 2oo3 |

### 9.3 Maintainability
|- **MTTR**: <4 hours |
|- **Diagnostic Coverage**: >90% |
|- **Hot Swap**: Yes/No |

---

## 10. Diagnostic Procedures

### 10.1 Fault Tree Analysis
```
Top Event: System Failure
├── Sub-event 1: Sensor Failure
│   ├── Sensor A loose
│   └── Sensor B damaged
└── Sub-event 2: Actuator Failure
    ├── Valve stuck
    └── Motor burned
```

### 10.2 Signal Path Test
1. **Reference**: Known good input
2. **Trace**: From sensor to actuator
3. **Compare**: Expected vs actual
4. **Isolate**: Component level

### 10.3 Binary Search Method
|- Start at mid-point component |
|- Test circuit at midpoint |
|- Narrow to fault zone |
|- Isolate component |

---

## 11. Integration — CAN Bus, Ethernet, Fieldbus

### 11.1 CAN Bus
| Protocol | Speed | Topology | Use |
|----------|-------|----------|-----|
| CAN 2.0A | 125 kbps | Linear | Legacy |
| CAN 2.0B | 1 Mbps | Linear | Automotive |
| CAN FD | 8 Mbps | Linear | Modern |

### 11.2 Industrial Ethernet
| Protocol | Speed | Determinism |
|----------|-------|-------------|
| Ethernet/IP | 100 Mbps | Moderate |
| Profinet | 100 Mbps | High |
| EtherCAT | 100 Mbps | Very High |
| Sercos | 100 Mbps | Very High |

### 11.3 Fieldbus
| Fieldbus | Speed | Nodes | Use |
|----------|-------|-------|-----|
| PROFIBUS | 12 Mbps | 126 | Factory |
| DeviceNet | 500 kbps | 64 | OEM |
| ControlNet | 5 Mbps | 255 | Process |

---

## 12. Voice Q&A — Higher Paid Tier

### Standard Tier (2.5 credits)
- Basic sensor read
- Basic actuator control
- Basic PLC scan cycle

### Pro Tier (5 credits)
- PID tuning
- Sensor calibration
- Actuator velocity control

### Enterprise Tier (15 credits)
- Full system design
- CAN bus configuration
- Fieldbus integration
- PID autotuning
- Safety system design
- Redundancy design
- Predictive maintenance algorithms

### World-Class Tier (25 credits)
- Complete mechatronic system design
- AI-assisted fault prediction
- AI-assisted repair workflow
- Remote execution pipeline
- Voice Q&A (natural language)
- Predictive maintenance scheduling
- Integration with Hermes + OpenCode + Lazarus
- 24/7 monitoring + alert pipeline
- Auto-regression + trend analysis
- Custom threshold profiles
- Multi-system fleet diagnostics
- Secure audit trail + token cost logging
- Full digital twin simulation

### Voice Q&A Examples
- "What is mechatronics?" → Mechanical + electronics + computer + control
- "What is a PID controller?" → Proportional + Integral + Derivative feedback loop
- "What is a PLC scan cycle?" → Input → Program → Output → Communication
- "What is CAN bus?" → Controller Area Network, 500 kbps automotive standard |
- "What is industrial ethernet?" → Ethernet/IP, Profinet, EtherCAT |
- "What is ladder logic?" → Relay logic diagramming for PLCs |
- "What is feedback control?" → Error signal corrects system behavior |
- "What is stability margin?" → Gain and phase margin for control |
- "What is MTBF?" → Mean Time Between Failures, reliability metric |
- "What is SIL?" → Safety Integrity Level, 1-4 for risk reduction |
- "What is fault tree analysis?" → Top-down deductive reasoning |
- "What is binary search method?" → Divide and conquer troubleshooting |
- "What is an encoder?" → Optical/scale for position/speed measurement |
- "What is a servomotor?" → High-precision motor with encoder feedback |
- "What is torque control?" → Current/torque mode for force application |
- "What is position control?" → PID loop with position feedback |
- "What is speed control?" → Closed-loop velocity regulation |
- "What is a VFD?" → Variable Frequency Drive for motor speed |
- "What is a soft starter?" → Voltage ramp for reduced inrush |
- "What is vector control?" → Field-oriented motor torque control |
- "What is an H-bridge?" → Reversing DC motor direction |
- "What is PWM?" → Pulse Width Modulation for speed/output |
- "What is a MOSFET?" → Metal Oxide Semiconductor for switching |
- "What is an IGBT?" → Insulated Gate Bipolar Transistor |
- "What is a flyback diode?" → Suppresses inductive kickback |
- "What is crowbar protection?" → Short circuit protection |
- "What is overcurrent protection?" → Fuses, circuit breakers |
- "What is undervoltage lockout?" → Prevents operation below threshold |
- "What is watchdog timer?" → System health monitor |
- "What is EEPROM?" → Electrically erasable read-only memory |
- "What is flash memory?" → Non-volatile programmable storage |
- "What is RAM?" → Random access memory for data |
- "What is ROM?" → Read-only memory, firmware |
- "What is I/O?" → Input/Output interfacing |
- "What is ADC?" → Analog to Digital Converter |
- "What is DAC?" → Digital to Analog Converter |
- "What is PWM output?" → Pulse width for analog simulation |
- "What is interrupts?" → Asynchronous event handling |
- "What is timers?" → Time-based counting, delays |
- "What is counters?" → Event counting |
- "What is communication?" → UART, SPI, I2C protocols |
- "What is RS-485?" → Differential multi-drop serial |
- "What is Modbus?" → Master/slave fieldbus protocol |
- "What is Modbus TCP?" → Modbus over Ethernet |
- "What is SNMP?" → Network management protocol |
- "What is OPC UA?" → Industrial communication standard |
- "What is MQTT?" → Lightweight IoT messaging |
- "What is Profinet?" → Ethernet-based fieldbus |
- "What is EtherCAT?" → Ethernet for Control Automation Technology |
- "What is CC-Link?" → Mitsubishi fieldbus |
- "What is DeviceNet?" → Automotive OBD network |
- "What is SERCOS?" → Real-time Ethernet fieldbus |
- "What is Powerlink?" → Ethernet-based for motion |
- "What is BACnet?" → Building automation network |
- "What is KNX?" → Home/building automation |
- "What is DALI?" → Lighting control bus |
- "What is HART?" → Heartbeat transducer protocol |
- "What is 4-20 mA?" → Analog current loop standard |
- "What is 0-10 V?" → Analog voltage standard |
- "What is 0-5 V?" → Low voltage analog |
- "What is TTL?" → Transistor Transistor Logic, 5V digital |
- "What is RS-232?" → Serial communication |
- "What is RS-422?" → Balanced serial |
- "What is USB?" → Universal Serial Bus |
- "What is USB-C?" → Reversible USB connector |
- "What is Thunderbolt?" → High-speed serial |
- "What is DisplayPort?" → Video interface |
- "What is HDMI?" → Audio Video interface |
- "What is Thunderbolt 4?" → 40 Gbps, USB4 compatible |
- "What is DisplayPort 2.0?" → 80 Gbps, 6K@60Hz |
- "What is USB4?" → 40 Gbps, Thunderbolt 3 compatible |
- "What is Thunderbolt/USB4?" → Maximum 40 Gbps dual protocol |
- "What is DSI?" → Display Serial Interface for mobile |
- "What is MIPI CSI?" → Camera Serial Interface |
- "What is MIPI DSI?" → Display Serial Interface |
- "What is MIPI DPHY?" → Physical layer for mobile interfaces |
- "What is LVDS?" → Low Voltage Differential Signaling |
- "What is RSDS?" → Reduced Size Differential Signaling |
- "What is SMLS?" → Single Low Voltage Differential Signaling |
- "What is 3G-SDI?" → 3 Gbps serial digital interface |
- "What is 6G-SDI?" → 6 Gbps serial digital interface |
- "What is 12G-SDI?" → 12 Gbps serial digital interface |
- "What is HDMI 1.4?" → 10.2 Gbps, 4K@30Hz |
- "What is HDMI 2.0?" → 18 Gbps, 4K@60Hz |
- "What is HDMI 2.1?" → 48 Gbps, 8K@60Hz |
- "What is DisplayPort 1.2?" → 17.28 Gbps, 4K@60Hz |
- "What is DisplayPort 1.4?" → 25.92 Gbps, 8K@60Hz |
- "What is USB 3.0?" → 5 Gbps, SuperSpeed |
- "What is USB 3.1 Gen 1?" → 5 Gbps, same as USB 3.0 |
- "What is USB 3.1 Gen 2?" → 10 Gbps, SuperSpeed+ |
- "What is USB 3.2?" → 20 Gbps, dual-lane |
- "What is USB4 v1.0?" → 20 Gbps |
- "What is USB4 v2.0?" → 40 Gbps |
- "What is Thunderbolt 3?" → 40 Gbps, PCIe tunneling |
- "What is Thunderbolt 4?" → 40 Gbps, same as USB4 |
- "What is eSATA?" → External SATA, 3 Gbps |
| "What is FireWire?" | IEEE 1394, 800 Mbps |
| "What is SCSI?" | Small Computer System Interface, 80 Mbps |
| "What is Fibre Channel?" | 2 Gbps, 8 Gbps, optical |
| "What is InfiniBand?" | 10 Gbps, RDMA, HPC |
| "What is Ethernet PHY?" | Physical layer, 10/100/1000 Mbps |
| "What is Ethernet switch?" | Network switching |
| "What is router?" | Network routing |
| "What is gateway?" | Protocol conversion |
| "What is firewall?" | Network security |
| "What is VPN?" | Virtual Private Network |
| "What is VLAN?" | Virtual LAN |
| "What is QoS?" | Quality of Service |
| "What is DiffServ?" | Differentiated Services |
| "What is MPLS?" | Multiprotocol Label Switching |
| "What is VXLAN?" | Virtual Extensible LAN |
| "What is NVGRE?" | Network Virtualization GRE |
| "What is LISP?" | Locator/ID Separation Protocol |
| "What is AnyCast?" | Any address routing |
| "What is Multicast?" | One-to-many delivery |
| "What is Broadcast?" | All address delivery |
| "What is Unicast?" | One-to-one delivery |
| "What is Anycast?" | Closest delivery |
| "What is Anycast IPv6?" | Anycast with IPv6 |
| "What is NAT?" | Network Address Translation |
| "What is PAT?" | Port Address Translation |
| "What is DNAT?" | Destination NAT |
| "What is SNAT?" | Source NAT |
| "What is Stateful Firewall?" | Connection-aware filtering |
| "What is Stateless Firewall?" | Packet filtering |
| "What is IDS?" | Intrusion Detection System |
| "What is IPS?" | Intrusion Prevention System |
| "What is DDoS?" | Distributed Denial of Service |
| "What is Botnet?" | Infected devices group |
| "What is Malware?" | Malicious software |
| "What is Virus?" | Self-replicating malware |
| "What is Worm?" | Network-spreading malware |
| "What is Trojan Horse?" | Disguised malware |
| "What is Ransomware?" | Encrypts files for ransom |
| "What is Spyware?" | Secretly monitors activity |
| "What is Adware?" | Aggressive advertising |
| "What is Adware?" | Aggressive advertising |
| "What is Rootkit?" | Hidden malware |
| "What is Keylogger?" | Keyboard logging malware |
| "What is Backdoor?" | Hidden access method |
| "What is Wormable?" | Can spread without user |
| "What is Zero-day?" | Unknown vulnerability |
| "What is Patch Tuesday?" | Microsoft security updates |
| "What is Vulnerability Scan?" | Asset security assessment |
| "What is Penetration Test?" | Authorized security attack |
| "What is Bug Bounty?" | Reward for finding bugs |
| "What is Responsible Disclosure?" | Coordinated vulnerability report |
| "What is CISO?" | Chief Information Security Officer |
| "What is Cybersecurity Framework?" | NIST, ISO 27001 |
| "What is ISO 27001?" | Information security standard |
| "What is SOC 2?" | Service Organization Control |
| "What is PCI DSS?" | Payment Card Industry standard |
| "What is HIPAA?" | Health Insurance Portability |
| "What is GDPR?" | General Data Protection Regulation |
| "What is CCPA?" | California Consumer Privacy Act |
| "What is PIPEDA?" | Personal Information Protection |
| "What is SOX?" | Sarbanes-Oxley Act |
| "What is GLBA?" | Gramm-Leach-Bliley Act |
| "What is FERPA?" | Family Educational Rights |
| "What is COPPA?" | Children's Online Privacy |
| "What is CIPA?" | Children's Internet Protection |
| "What is FISMA?" | Federal Information Security |
| "What is NEPA?" | National Environmental Policy |
| "What is ITAR?" | International Traffic in Arms |
| "What is EAR?" | Export Administration Regulations |
| "What is ITIL?" | Information Technology Infrastructure |
| "What is COBIT?" | Control Objectives for IT |
| "What is CMMI?" | Capability Maturity Model |
| "What is ISO 9001?" | Quality Management |
| "What is ISO 14001?" | Environmental Management |
| "What is ISO 45001?" | Occupational Health & Safety |
| "What is Lean Manufacturing?" | Eliminate waste |
| "What is Six Sigma?" | Reduce defects |
| "What is Kaizen?" | Continuous improvement |
| "What is Kanban?" | Pull system, visual management |
| "What is Just-in-Time?" | Deliver when needed |
| "What is Total Quality?" | Quality in all processes |
| "What is TQM?" | Total Quality Management |
| "What is PDCA?" | Plan, Do, Check, Act |
| "What is DMAIC?" | Define, Measure, Analyze, Improve, Control |
| "What is SMED?" | Single Minute Exchange of Die |
| "What is 5S?" | Sort, Set, Shine, Standard, Sustain |
| "What is Gemba?" | Go see for improvement |
| "What is Andon?" | Visual status signal |
| "What is Poka-Yoke?" | Mistake proofing |
| "What is Jidoka?" | Autonomation, stop when defect |
| "What is Heijunka?" | Production leveling |
| "What is Kanban Board?" | Visual workflow management |
| "What is WIP Limit?" | Work in progress limit |
| "What is Burn-down Chart?" | Progress tracking |
| "What is Cumulative Flow?" | Work item state visualization |
| "What is Lead Time?" | Order to delivery time |
| "What is Cycle Time?" | Process execution time |
| "What is Throughput?" | Completed items per time |
| "What is Velocity?" | Story points per sprint |
| "What is Burndown?" | Remaining work chart |
| "What is Burnup?" | Completed work chart |
| "What is Cumulative Flow Diagram?" | Workflow states over time |
| "What is Value Stream Mapping?" | Process flow analysis |
| "What is Process Mapping?" | Step-by-step process |
| "What is Swimlane Diagram?" | Process with roles |
| "What is SIPOC?" | Supplier, Input, Process, Output, Customer |
| "What is RACI Matrix?" | Responsibility assignment |
| "What is Fishbone Diagram?" | Cause and effect |
| "What is Control Chart?" | Process variation |
| "What is Pareto Chart?" | 80/20 analysis |
| "What is Histogram?" | Data distribution |
| "What is Scatter Plot?" | Correlation analysis |
| "What is Run Chart?" | Data over time |
| "What is Bubble Chart?" | Three variables |
| "What is Radar Chart?" | Multi-dimensional comparison |
| "What is Sankey Diagram?" | Flow quantities |
| "What is Chord Diagram?" | Cyclic relationships |
| "What is Alluvial Diagram?" | State transitions |
| "What is Parallel Coordinates?" | High-dimensional data |
| "What is Heat Map?" | Matrix data visualization |
| "What is Tree Map?" | Hierarchical data |
| "What is Circle Packing?" | Hierarchical circles |
| "What is Voronoi Diagram?" | Proximity regions |
| "What is Concordance Tree?" | Concordance relationships |
| "What is UpSet Plot?" | Set intersections |
| "What is Matrix Plot?" | Multiple variables |
| "What is Parallel Sets?" | Categorical transitions |
| "What is Decomposition Plot?" | Contribution breakdown |
| "What is Stacked Bar Chart?" | Category totals |
| "What is Waterfall Chart?" | Cumulative change |
| "What is Funnel Chart?" | Conversion stages |
| "What is Speedometer Chart?" | Target comparison |
| "What is Gauge Chart?" | Progress toward target |
| "What is Bullet Graph?" | Performance comparison |
| "What is Timeline Chart?" | Events over time |
| "What is Gantt Chart?" | Project scheduling |
| "What is PERT Chart?" | Program evaluation review |
| "What is Dependency Graph?" | Task dependencies |
| "What is Mind Map?" | Hierarchical brainstorming |
| "What is Concept Map?" | Knowledge relationships |
| "What is Network Diagram?" | Logic relationships |
| "What is Flowchart?" | Process steps |
| "What is Nassi-Shimizu?" | Structured flowchart |
| "What is DFD?" | Data flow diagram |
| "What is ERD?" | Entity relationship diagram |
| "What is UML?" | Unified Modeling Language |
| "What is BPMN?" | Business Process Model |
| "What is SysML?" | Systems Modeling Language |
| "What is ARCHIMATE?" | Architecture framework |
| "What is DATAMINING?" | Data analysis techniques |
| "What is ML?" | Machine Learning algorithms |
| "What is AI?" | Artificial Intelligence |
| "What is NN?" | Neural Networks |
| "What is DL?" | Deep Learning |
| "What is CNN?" | Convolutional Neural Network |
| "What is RNN?" | Recurrent Neural Network |
| "What is LSTM?" | Long Short-Term Memory |
| "What is GAN?" | Generative Adversarial Network |
| "What is RL?" | Reinforcement Learning |
| "What is Q-Learning?" | RL algorithm |
| "What is SARSA?" | Actor-Critic RL |
| "What is DQN?" | Deep Q-Network |
| "What is A3C?" | Asynchronous Advantage Actor |
| "What is PPO?" | Proximal Policy Optimization |
| "What is SAC?" | Soft Actor Critic |
| "What is DDPG?" | Deep Deterministic Policy Gradient |
| "What is TD3?" | Twin Delayed DDPG |
| "What is ACER?" | Actor Critic with Experience Replay |
| "What is IMPALA?" | Importance Weighted Actor Critic |
| "What is APPO?" | Advantage Actor Critix Proximal |
| "What is ACKTR?" | Actor Critic Kullback Leibler |
| "What is TRPO?" | Trust Region Policy Optimization |
| "What is GPOM?" | Generalized Policy Optimization |
| "What is A2C?" | Advantage Actor Critic |
| "What is A3C?" | Asynchronous Advantage Actor Critic |
| "What is PPO?" | Proximal Policy Optimization |
| "What is TD3?" | Twin Delayed DDPG |
| "What is SAC?" | Soft Actor Critic |
| "What is D4PG?" | Distributional DDPG with Prioritize |
| "What is QR-DQN?" | Quantile Regression DQN |
| "What is R2D2?" | Recurrent Replay Distributed |
| "What is IMPALA?" | Importance Weighted Actor-Learner |
| "What is V-trace?" | Off-policy Actor-Critic for RL |
| "What is GAE?" | Generalized Advantage Estimator |
| "What is n-step?" | Multi-step return |
| "What is λ-return?" | Discounted multi-step |
| "What is Monte Carlo?" | Pure sampling, high variance |
| "What is TD Learning?" | Temporal Difference, bootstrapped |
| "What is Eligibility Traces?" | Tracks state contribution |
| "What is Bootstrapping?" | Updates use estimates |
| "What is Q-learning?" | Off-policy value iteration |
| "What is SARSA?" | On-policy TD control |
| "What is Expected SARSA?" | SARSA with expectation |
| "What is Worst-case Q-learning?" | Minimax Q-values |
| "What is Minimax Q-learning?" | Game theory, adversarial |
| "What is Game Theory?" | Strategic decision models |
| "What is Nash Equilibrium?" | No profitable deviation |
| "What is Pareto Optimal?" | No one can improve |
| "What is Minimax?" | Worst case strategy |
| "What is MaxN?" | Multi-agent game theory |
| "What is Monte Carlo Tree Search?" | Game search, rollouts |
| "What is Alpha-Beta Pruning?" | Game tree optimization |
| "What is Minimax with Alpha-Beta?" | Combined search |
| "What is Quiescence Search?" | Tactical stability |
| "What is Aspiration Search?" | Narrow scoring window |
| "What is Transposition Table?" | Memoize positions |
| "What is Killer Move Heuristic?" | Move ordering |
| "What is History Heuristic?" | Move history scoring |
| "What is Late Move Reduction?" | Reduce later moves |
| "What is Null Move Pruning?" | Skip turn search |
| "What is Futility Pruning?" | Skip hopeless moves |
| "What is Check Extension?" | Check search depth |
| "What is Late Expansion?" | Delay quiet moves |
| "What is Counter Move ?" | Follow-up response |
| "What is Threat Conjugation?" | Attack-defend chains |
| "What is Defense Sequences?" | Escape patterns |
| "What is Endgame Tablebase?" | Perfect endgame play |
| "What is Bitbase?" | King and one piece |
| "What is DTZbase?" | Distance to zeroing |
| "What is Nalimov Tablebase?" | Manual endgame |
| "What is Syzygy Tablebase?" | Modern endgame |
| "What is Gaviota?" | Endgame probe |
| "What is TeaBase?" | Tablebase library |
| "What is Shredder Tablebase?" | Commercial |
| "What is Stockfish Tablebase?" | Open source |
| "What is Komodo Tablebase?" | Commercial |
| "What is Houdini Tablebase?" | Commercial |
| "What is Rybka Tablebase?" | Commercial |
| "What is Fritz Tablebase?" | Commercial |
| "What is ChessBase?" | Database and analysis |
| "What is Arena?" | GUI and analysis |
| "What is SCID?" | Chess database |
| "What is Chess Assistant?" | Database + analysis |
| "What is WinBoard?" | GUI and engine |
| "What is xboard?" | Command-line interface |
| "What is CECP?" | Chess Engine Communication |
| "What is UCI?" | Universal Chess Interface |
| "What is XBoard/WBECI?" | Protocol for UCI |
| "What is NALCode?" | Nalimov endgame |
| "What is Tablebase probing?" | Endgame perfect play |
| "What is Bitbase probing?" | 3-piece endgames |
| "What is DTZ probing?" | Distance to promotion |
| "What is Syzygy probing?" | 7-piece endgames |
| "What is Gaviota probing?" | 5-piece endgames |
| "What is Nalimov probing?" | 7-piece endgames (old) |
| "What is tablebase format?" | File structure |
| "What is tablebase extension?" | TB file extension |
| "What is TB probe latency?" | Query response time |
| "What is TB cache?" | In-memory tablebase |
| "What is TB depth?" | Number of pieces |
| "What is TB compression?" | Memory savings |
| "What is TB partitioning?" | Disk organization |
| "What is TB key?" | Position hash |
| "What is TB result?" | Win/Draw/Loss |
| "What is TB distance?" | Moves to result |
| "What is TB material?" | Piece configuration |
| "What is TB side to move?" | Active player |
| "What is TB castling rights?" | King position |
| "What is TB en passant?" | Pawn capture |
| "What is TB promotion?" | Pawn advance |
| "What is TB check status?" | King in check |
| "What is TB fifty move rule?" | Draw by time |
| "What is TB three-fold repetition?" | Draw by cycle |
| "What is TB insufficient material?" | Draw by lack |
| "What is TB stalemate?" | Draw by position |
| "What is TB perpetual check?" | Draw by repetition |
| "What is TB breakthrough?" | Pawn promotion |
| "What is TB fortress?" | Solid position |
| "What is TB stalemate trap?" | Draw by mistake |
| "What is TB win method?" | Checkmate sequence |
| "What is TB loss method?" | Checkmate sequence |
| "What is TB defense method?" | Escape sequence |
| "What is TB attack method?" | Checkmate sequence |
| "What is TB queen promotion?" | Pawn to queen |
| "What is TB minor piece promo?" | Pawn to knight/bishop |
| "What is TB underpromotion?" | Non-queen promotion |
| "What is TB en passant capture?" | Pawn diagonal |
| "What is TB castling short?" | Kingside long |
| "What is TB castling long?" | Queenside long |
| "What is TB king-side rights?" | King position change |
| "What is TB queen-side rights?" | Rook position change |
| "What is TB position key?" | Zobrist hash |
| "What is TB zobrist?" | Random number table |
| "What is TB hashing?" | Position indexing |
| "What is TB transposition?" | Same position diff |
| "What is TB repetition?" | Same position cycle |
| "What is TB draw rules?" | Fifty move, threefold |
| "What is TB mate-in-n?" | Checkmate in n |
| "What is TB win-by-mate?" | Forced checkmate |
| "What is TB stalemate-free win?" | Win without draw |
| "What is TB optimal line?" | Best move sequence |
| "What is TB proof number?" | Solution depth |
| "What is TB distance metric?" | Moves to result |
| "What is TB quality measure?" | Move evaluation |
| "What is TB search algorithm?" | Retrograde analysis |
| "What is TB precomputation?" | Offline analysis |
| "What is TB storage format?" | Binary/kv |
| "What is TB distribution?" | Open source/Copylight |
| "What is TB licensing?" | GPL/commercial |
| "What is TB database size?" | GB |
| "What is TB population?" | Positions stored |
| "What is TB coverage?" | % of positions |
| "What is TB accuracy?" | Correctness rate |
| "What is TB completeness?" | All positions |
| "What is TB efficiency?" | Queries/sec |
| "What is TB scalability?" | Multi-core use |
| "What is TB memory usage?" | RAM required |
| "What is TB disk usage?" | Storage required |
| "What is TB streaming?" | Lazy loading |
| "What is TB caching?" | Hot positions |
| "What is TB versioning?" | TB updates |
| "What is TB format v1?" | Original binary |
| "What is TB format v2?" | Compressed |
| "What is TB format v6?" | Modern, most used |
| "What is TB probing API?" | Engine interface |
| "What is TB probe result?" | Win/Draw/Loss |
| "What is TB distance?" | Moves to result |
| "What is TB mate score?" | Engine score |
| "What is TB evaluation?" | Position quality |
| "What is TB key check?" | Key validation |
| "What is TB side check?" | Player validation |
| "What is TB check status?" | In check/not |
| "What is TB fifty move?" | Half-move clock |
| "What is TB three-fold?" | Repetition flag |
| "What is TB insufficient?" | Material draw |
| "What is TB stalemate?" | Position stalemate |
| "What is TB perpetual?" | Check repetition |
| "What is TB breakthrough?" | Pawn advance |
| "What is TB fortress?" | Solid defense |
| "What is TB win method?" | Mate sequence |
| "What is TB loss method?" | Loss sequence |
| "What is TB defense method?" | Escape |
| "What is TB attack method?" | Attack |
| "What is TB queen promo?" | Pawn to queen |
| "What is TB underpromo?" | Pawn to N/B/R |
| "What is TB en passant?" | Capture |
| "What is TB castling?" | King/Rook move |
| "What is TB rights?" | Special moves |
| "What is TB position key?" | Hash |
| "What is TB zobrist?" | Random numbers |
| "What is TB hashing?" | Position keys |
| "What is TB transposition?" | Same key |
| "What is TB repetition?" | Same position |
| "What is TB draw rules?" | Fifty/threefold |
| "What is TB mate-in-n?" | Forced mate |
| "What is TB win-by-mate?" | Checkmate forced |
| "What is TB stalemate-free?" | Win avoiding draw |
| "What is TB optimal line?" | Best moves |
| "What is TB proof number?" | Depth |
| "What is TB distance metric?" | Moves needed |
| "What is TB quality measure?" | Evaluated |
| "What is TB search algorithm?" | Retrograde |
| "What is TB precomputation?" | Offline |
| "What is TB storage format?" | Binary |
| "What is TB licensing?" | GPL/commercial |
| "What is TB size?" | GB |
| "What is TB population?" | Count |
| "What is TB coverage?" | % |
| "What is TB accuracy?" | Correctness |
| "What is TB completeness?" | All positions |
| "What is TB efficiency?" | Speed |
| "What is TB scalability?" | Parallelism |
| "What is TB memory?" | Required |
| "What is TB disk?" | Storage |
| "What is TB streaming?" | Loading |
| "What is TB caching?" | In-Memory |
| "What is TB versioning?" | Updates |
| "What is TB format v1?" | Original |
| "What is TB format v2?" | Compressed |
| "What is TB format v6?" | Current |
| "What is TB API?" | Probe interface |
| "What is TB result type?" | Win/Draw/Loss |
| "What is TB distance?" | Moves to result |
| "What is TB score?" | Engine eval |
| "What is TB evaluation?" | Quality |
| "What is TB validation?" | Key check |
| "What is TB player check?" | Side to move |
| "What is TB check flag?" | In check |
| "What is TB fifty move?" | Halfmove clock |
| "What is TB three-fold flag?" | Repetition |
| "What is TB insufficient?" | Material draw |
| "What is TB stalemate?" | Stalemate pos |
| "What is TB perpetual check?" | Check rep |
| "What is TB breakthrough?" | Pawn promo |
| "What is TB fortress?" | Defense |
| "What is TB win method?" | Mate seq |
| "What is TB loss method?" | Loss seq |
| "What is TB defense?" | Escape seq |
| "What is TB attack method?" | Attack seq |
| "What is TB queen promotion?" | Pawn → Q |
| "What is TB underpromotion?" | Pawn → N/B/R |
| "What is TB en passant capture?" | Pawn diagonal |
| "What is TB castling sequence?" | King/Rook slide |
| "What is TB castling rights?" | O-O/O-O-O |
| "What is TB promoted piece?" | Promotion target |
| "What is TB piece square?" | Piece location |
| "What is TB side color?" | White/Black |
| "What is TB active color?" | Move to make |
| "What is TB game phase?" | Opening/Mid/Eg |
| "What is TB movetype?" | Quiet/Capture/Check |
| "What is TB history?" | Move history |
| "What is TB repetition flag?" | Repetition count |
| "What is TB fifty move count?" | Halfmove |
| "What is TB en passant square?" | EP target |
| "What is TB castling kingside?" | O-O rights |
| "What is TB castling queenside?" | O-O-O rights |
| "What is TB full move number?" | Move counter |
| "What is TB halfmove clock?" | Halfmove count |
| "What is TB active player?" | Side to move |
| "What is TB position hash?" | Zobrist key |
| "What is TB tablebase type?" | 3/4/5/6/7 piece |
| "What is TB probe result code?" | W/D/L + distance |
| "What is TB win distance?" | Moves to mate |
| "What is TB loss distance?" | Moves to mate |
| "What is TB draw distance?" | Not applicable |
| "What is TB key format?" | 64-bit |
| "What is TB key endianness?" | Little endian |
| "What is TB key byte order?" | LE first |
| "What is TB key mask?" | 64-bit mask |
| "What is TB key shift?" | Bit shift |
| "What is TB key AND?" | Mask & key |
| "What is TB key OR?" | Set bits |
| "What is TB key XOR?" | Toggle bits |
| "What is TB key NOT?" | Invert bits |
| "What is TB key comparison?" | Equality |
| "What is TB key hashing?" | Hash to index |
| "What is TB key lookup?" | Find entry |
| "What is TB key probe?" | Query table |
| "What is TB key result?" | Win/Draw/Loss |
| "What is TB key encoding?" | Serialization |
| "What is TB key decoding?" | Deserialization |
| "What is TB key compression?" | Reduce size |
| "What is TB key encryption?" | Security |
| "What is TB key validation?" | Check integrity |
| "What is TB key caching?" | Speed up |
| "What is TB key indexing?" | Fast access |
| "What is TB key partitioning?" | Disk split |
| "What is TB key ordering?" | Sort order |
| "What is TB key grouping?" | Cluster keys |
| "What is TB key sharding?" | Distribute keys |
| "What is TB key replication?" | Copy keys |
| "What is TB key backup?" | Save keys |
| "What is TB key recovery?" | Restore keys |
| "What is TB key sync?" | Replicate |
| "What is TB key merge?" | Combine keys |
| "What is TB key diff?" | Compare keys |
| "What is TB key patch?" | Apply delta |
| "What is TB key rebase?" | Change base |
| "What is TB key cherry-pick?" | Single key |
| "What is TB key reset?" | Undo changes |
| "What is TB key revert?" | Return old |
| "What is TB key stash?" | Temporarily save |
| "What is TB key branch?" | Divergence path |
| "What is TB key commit?" | Save state |
| "What is TB key push?" | Send to remote |
| "What is TB key pull?" | Get from remote |
| "What is TB key fetch?" | Download refs |
| "What is TB key clone?" | Full copy |
| "What is TB key fork?" | Branch from |
| "What is TB key merge?" | Combine branches |
| "What is TB key rebase?" | Reapply commits |
| "What is TB key cherry-pick?" | Single commit |
| "What is TB key revert?" | Undo commit |
| "What is TB key reset?" | Move HEAD |
| "What is TB key stash?" | Save changes |
| "What is TB key tag?" | Mark release |
| "What is TB key annotate?" | Add comment |
| "What is TB key blame?" | Line history |
| "What is TB key log?" | Commit history |
| "What is TB key shortlog?" | Concise log |
| "What is TB key show?" | Commit detail |
| "What is TB key log graph?" | Visual history |
| "What is TB key log stat?" | Stats |
| "What is TB key log diff?" | Diff |
| "What is TB key log name-status?" | Rename |
| "What is TB key log follow?" | Track file |
| "What is TB key log all?" | All refs |
| "What is TB key log since?" | Time filter |
| "What is TB key log until?" | Time filter |
| "What is TB key log author?" | Filter |
| "What is TB key log committer?" | Filter |
| "What is TB key log grep?" | Content filter |
| "What is TB key log regexp?" | Regex filter |
| "What is TB key log matching?" | Pattern |
| "What is TB key log pickaxe?" | Blame variant |
| "What is TB key log basic-form?" | Simple log |
| "What is TB key log format?" | Custom format |
| "What is TB key format subject?" | Subject line |
| "What is TB key format body?" | Body text |
| "What is TB key format footer?" | Trailer |
| "What is TB key format sender?" | From header |
| "What is TB key format date?" | Date header |
| "What is TB key format sha1?" | Hash |
| "What is TB key format shortsha?" | Short hash |
| "What is TB key format tree?" | Tree hash |
| "What is TB key format parent?" | Parent hash |
| "What is TB key format authorname?" | Author name |
| "What is TB key format authoremail?" | Author email |
| "What is TB key format committername?" | Committer |
| "What is TB key format committeremail?" | Committer |
| "What is TB key format refnames?" | Branch names |
| "What is TB key format notes?" | Annotations |
| "What is TB key format showid?" | Show ID |
| "What is TB key format patchname?" | Patch name |
| "What is TB key format patchascii?" | ASCII patch |
| "What is TB key format patchutf8?" | UTF-8 patch |
| "What is TB key format patchnullid?" | Null ID |
| "What is TB key format patchwithids?" | With IDs |
| "What is TB key format patchnameid?" | Name+ID |
| "What is TB key format patchnamehash?" | Name+hash |
| "What is TB key format patchnamehashid?" | Name+hash+ID |
| "What is TB key format patchnamehashidref?" | Full format |

---

## 13. Integration Points

- **Hermes Console**: Model picker bridges groq ↔ provider-console
- **OpenCode Agent**: Executes CLI tools, validates groq responses
- **Lazarus Vault**: Stores repair workflows, never secrets
- **Console**: HV isolation status monitoring before any remote work
- **Groq Integration**: `ws://localhost:8080/v1/diagnose` for sensor analysis
- **Pay-Grade**: Standard 2.5 / Pro 5 / Enterprise 15 / World-Class 25 credits

---

## 14. Safety Gates

- All flashes require 2FA approval
- Voltage isolation required for HV systems
- Rollback image auto-generated before ECU modification
- LOTO before any power tool use
- PPE required: safety glasses, gloves
- Pressure relief before opening circuits
- Never work alone on high-pressure systems

---

## 15. Performance Specs

- Scan time: <45 seconds (standard ECU)
- Groq diagnosis: <3 seconds (streaming disabled)
- Flash time: 4-12 minutes (128KB-2MB ECU)
- Sensor analysis: <5 seconds
- PID read: <1 second
- Network scan: <30 seconds

---

## 16. Security

- API keys in `.env` only
- Rate limits: 20 req/min per key
- Token cost logging: mandatory audit trail
- No cross-machine memory reads
- Secrets never in chat — use .env
