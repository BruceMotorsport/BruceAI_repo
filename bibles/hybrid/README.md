# Hybrid Bible — Automotive Diagnostics & Integration

## World-Class Diagnostic Framework

### 1. Protocol Mastery
- **CAN Bus Architecture**: Dual-500kΩ termination, 500k baud, J1939, OBD2-CAN
- **K-Line/L-Line**: 10.4kbps startup, 5-baud init, ECU wake sequences
- **LIN Bus**: Short-range, low-speed, master-slave architecture

### 2. ECU Communication Stack
```
Application Layer (DTS, UDS, OBD2)
↑ Transport Layer (ISO-TP, UDS TPD)
↑ Network Layer (CAN, L-Line, K-Line)
↑ Physical Layer (12V CAN, 5V K, 12V L)
```

### 3. Vehicle Categories
| Category | Protocols | Tool | Voltage |
|----------|-----------|------|---------|
| Gasoline OBD2 | CAN, K-Line | X431 | 12V |
| Diesel Common Rail | CAN, J1939 | EDC17 | 12V |
| Heavy Duty | J1939,  CAN | Techstream | 24V |
| Hybrid/EV | CAN, LIN | OBD2-CAN | 400V |

### 4. Groq Integration Protocol
```
WebSocket: ws://localhost:8080/v1/diagnose
Payload:
{
  "model": "groq-qwen-14b",
  "messages": [
    {"role": "user", "content": "diagnostic query"}
  ],
  "streaming": false
}
```

### 5. Pay-Grade Escalation
- **Standard**: Basic OBD2 DTC read (GROQ: 2.5 credits)
- **Pro**: Bi-directional control + coding (GROQ: 5 credits)
- **Enterprise**: Full ECU flash + adaptation (GROQ: 15 credits)
- **World-Class**: AI-assisted fault prediction + repair workflow (GROQ: 25 credits)

### 6. Remote Execution Pipeline
1. `SCAN_RESULTS = query_victim_sensor()`
2. `ANALYSIS = groq_diagnose(SCAN_RESULTS)`
3. `REPAIR = groq_generate_fix(ANALYSIS)`
4. `EXECUTION = opencode_execute(REPAIR)`

### 7. Safety Gates
- All flashes require 2FA approval
- Voltage isolation required for HV systems
- Rollback image auto-generated before ECU modification

### 8. Integration Points
- **Hermes Console**: Model picker bridges groq ↔ provider-console
- **OpenCode Agent**: Executes CLI tools, validates groq responses
- **Lazarus Vault**: Stores repair workflows, never secrets

### 9. Performance Specs
- Scan time: <45 seconds (standard ECU)
- Groq diagnosis: <3 seconds (streaming disabled)
- Flash time: 4-12 minutes (128KB-2MB ECU)

### 10. Security
- API keys in `.env` only
- Rate limits: 20 req/min per key
- Token cost logging: mandatory audit trail
- No cross-machine memory reads