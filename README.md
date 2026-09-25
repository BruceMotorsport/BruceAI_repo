# BruceAI Server Setup

## Install (per machine)

1. Extract to `C:\Users\<user>\BruceAI\`
2. Configure `.env` with your own keys:
   ```
   # Each machine gets its OWN Groq key
   GROQ_API_KEY=<YOUR_GROQ_KEY>
   
   # Each machine gets its OWN OpenRouter key
   OPENROUTER_API_KEY=<YOUR_OPENROUTER_KEY>
   
   # Shared OpenCode key (same value across all machines)
   OPENCODE_API_KEY=<SHARED_OPENCODE_KEY>
   ```
3. Start Groq bridge: `python groq_bridge.py --port 8080 --api-key $GROQ_API_KEY`
4. Start Provider Console: `python main.py` (port 9001)
5. Configure Hermes `config.yaml`:
   ```yaml
   custom_providers:
     - name: BruceAI
       base_url: http://127.0.0.1:9001/v1
       api_key: "<SHARED_OPENCODE_KEY>"
       api_mode: openai
   ```
6. Verify:
   ```bash
   curl http://127.0.0.1:8080/health   # {"status":"ok","models":7}
   curl http://127.0.0.1:9001/health   # {"status":"ok","port":9001}
   ```

## Key Rules
- OpenCode key: SHARED across all machines
- Groq key: each machine's OWN
- OpenRouter key: each machine's OWN
- Never share secrets in chat

## Files
- `main.py` — Provider Console (FastAPI, :9001)
- `groq_bridge.py` — Groq bridge (:8080, 7 models)
- `config.yaml` — Hermes provider template
