# BruceAI Server Setup

Persistent stack for this machine:

| Service | Port | File |
|---|---|---|
| Groq Bridge | 8080 | `groq_bridge.py` |
| Provider Console | 9001 | `main.py` |

## Quick start

```powershell
# start both, kill anything already on 8080/9001, health-check, run a real completion
.\start_bruceai.ps1 Start -SmokeTest

# live status: supervisor, port owners, health JSON, key sources, auto-start
.\start_bruceai.ps1 Status

# stop everything (also stops the supervisor so it does not restart them)
.\start_bruceai.ps1 Stop

# start + stay resident and repair the services if they die
.\start_bruceai.ps1 Supervise
```

`start_bruceai.bat` is the same thing for double-click / cmd use.

## Auto-start on boot

```powershell
.\start_bruceai.ps1 InstallTask        # register the auto-start
.\start_bruceai.ps1 UninstallTask      # remove it
```

* Registers a Task Scheduler job (`BruceAI Services`: logon +5s, boot +30s, restart on failure).
* If Task Scheduler refuses registration (UAC / non-elevated shell) it **falls back to the
  Startup folder** — `...\Start Menu\Programs\Startup\BruceAI Services.lnk` — which needs no
  elevation and starts the same supervisor at every logon.
* Only one supervisor runs at a time (`logs\supervisor.pid`).

After `InstallTask`, the supervisor starts the services itself at logon, so a manual
`Start` is only needed for the current session.

## Why the ports used to be busy (Errno 10048)

Two things were starting these files:

1. Manual foreground runs that stayed alive after the terminal closed.
2. Hermes' gateway agent shell running `cd C:\Users\USER\BruceAI && python main.py`.

`Start` therefore kills every listener on 8080/9001 before launching, waits for the ports to
be free, then health-checks both services. Running it twice in a row is safe.

## Keys

Read from `.env` in this folder at run time — never hardcoded, never printed.

```
GROQ_API_KEY=...          # this machine's own Groq key
OPENROUTER_API_KEY=...    # this machine's own OpenRouter key
OPENCODE_API_KEY=...      # shared across machines
```

* A placeholder or empty value is never exported, so `/health` reports
  `openrouter_configured: false` honestly instead of failing later.
* If `GROQ_API_KEY` / `OPENROUTER_API_KEY` are still placeholders, the launcher falls back to
  the real keys already present in `%LOCALAPPDATA%\hermes\profiles\*\.env`.
* Logs record the source and length of each key, never the value.

## Hermes (model picker)

The entry belongs in the config of the **profile Hermes actually loads**, not the root config:

```yaml
# %LOCALAPPDATA%\hermes\profiles\<profile>\config.yaml
custom_providers:
  - name: BruceAI
    base_url: http://127.0.0.1:9001/v1
    api_key: "${OPENCODE_API_KEY}"
    api_mode: openai
    models:
      openai/gpt-oss-120b: {}
      # ... one entry per model served by :9001/v1/models ...
```

* `hermes gateway run --profile X` sets `HERMES_HOME` to `profiles\X\`, so a root-level
  `custom_providers` block is invisible to it.
* `start_simone.bat` waits (max 45s) for `:9001/health` before launching the gateway, so the
  console is up before Hermes builds the picker.

## Verify

```powershell
curl http://127.0.0.1:8080/health   # {"status":"ok","models":7}
curl http://127.0.0.1:9001/health   # {"status":"ok","port":9001,"groq_bridge":"healthy",...}
curl http://127.0.0.1:9001/v1/models
```

## Files

- `start_bruceai.ps1` — manager: Start / Stop / Restart / Status / Supervise / InstallTask
- `start_bruceai.bat` — wrapper
- `groq_bridge.py` — Groq bridge (:8080, 7 models)
- `main.py` — Provider Console (:9001, routes Groq / OpenCode / OpenRouter)
- `env_loader.py` — loads `.env` (with the Hermes-profile fallback) when a service is run by hand
- `logs/` — service stdout/stderr plus `bruceai_YYYYMMDD.log`

## Key rules

- OpenCode key: SHARED across all machines
- Groq key: each machine's OWN
- OpenRouter key: each machine's OWN
- Never share secrets in chat; `.env` is gitignored
