# AI Help Desk — Bruce AI Cloud Console

## Purpose: Side-by-Side Customer Support
When a user (or their site) hits an issue, they open this. A human agent (Simone) monitors and responds in real-time, guided by this playbook.

---

## Issue 1: Compromised API Key
**Customer says:** "My site isn't working / I'm being billed too much / I think my key leaked"

**Agent steps (side-by-side):**
1. Verify the user's `api_key` via admin endpoint (`GET /api/v1/admin/slugs` or DB check — not exposed to user)
2. Check usage log (`security/security_events.log` or console DB `usage` table) — look for spike in `tokens_consumed`
3. If drain detected:
   - Revoke key (`DELETE /api/v1/admin/keys/revoke` — add this endpoint if missing)
   - Issue new key (`POST /api/v1/keys/generate` with same `user_id` and `product_slug`)
   - Log revocation + new key creation
4. Confirm new key works (`POST /api/chat` test with new key, minimal tokens)
5. Guide user to update site config (`BRUCE_API_KEY` variable) — provide exact command:
   ```bash
   # On site server (Vercel/env file update):
   # Replace BRUCE_API_KEY=ggc_li_old... with new key
   # Verify: curl -H "Authorization: Bearer <new_key>" http://127.0.0.1:8000/api/v1/slugs
   ```

**What NOT to do:** Never ask user to share old key in chat. Never regenerate without revoking (prevents double-spend tracking errors).

---

## Issue 2: Auth Failure / Key Rejected
**Customer says:** "My key says unauthorized / rate limited / expired"

**Agent steps:**
1. Check key format — must be `ggc_live_[64-char-hex]`
2. Check expiration (`expires` field from DB)
3. Check tier (`free_tier_unlimited` vs `pre_pay_yearly`) — compare rate limits
4. Check `/api/v1/admin/incidents` — if IP has 3+ hits, auto-blocked for 60 min
5. If rate limited: explain limit (e.g., 100 rpm for monthly tier). Offer upgrade or wait.
6. If blocked: explain why (honeypot hits, rapid failed auth). Unblock manually if false positive.

---

## Issue 3: Script Injection Attempt
**Customer says:** Nothing — agent detects via logs.
**Agent steps (automated + manual):**
1. `security/security_events.log` shows `ATTEMPT` entries with injection patterns
2. `sanitize_input.py` should have stripped/block payload — verify it ran
3. Check `/sites/` endpoints — CSP headers (`X-Frame-Options: DENY`, CSP policy) should prevent execution
4. If payload reached server: block IP (`security/ip_blocks.json` updated by `IPTracker`), notify customer only if their account was targeted (not attacker), and guide them to update `.env` permissions

---

## Issue 4: Rate Limit Hit / Token Exhausted
**Agent steps:**
1. Check `usage` DB table — confirm tokens used vs quota
2. If quota exceeded: explain billing tier (`pre_pay_monthly` = 2,000/month). Offer upgrade (`pre_pay_yearly` for 25,000)
3. Confirm no double-charging — webhook (`/webhooks/stripe`) should match usage

---

## Issue 5: Customer Can't Access Dashboard / Monitor
**Agent steps:**
1. Confirm `GET /api/v1/monitoring/dashboard` returns JSON (not 500)
2. Check `security/security_events.log` — any IP blocks blocking legitimate access?
3. Confirm CSP headers don't block dashboard resources (should be `default-src 'self'` — dashboard is same origin)

---

## Security Playbook — Quick Reference
| Threat | Defense | Tool / File |
|--------|---------|------------|
| XSS / Script injection | CSP + sanitize | `security/sanitize_input.py`, middleware headers |
| Clickjacking | X-Frame-Options | Middleware (`DENY`) |
| Key theft (direct drain) | Key separation (site ≠ provider) | `.env` never on site; site uses `ggc_live_*` |
| IP abuse | Auto-block (3 attempts / 60 min) | `security/ip_tracker.py` |
| Honeypot access | Log + redirect | Middleware (`/internal/dump-keys` etc.) |
| Auth failure | Key validation + DB check | `GET /api/v1/slugs` + DB `users` table |

---

## Prompt Template for Simone (Self-Reference)
When Simone is working and hits an issue, she reads this file first. Then she runs:
```bash
# Check current status
python -m uvicorn cloud-console.core:app --port 8000  # if console running
curl -I http://127.0.0.1:8000/  # verify headers
# Check logs
cat security/security_events.log  # or open in editor
# Block/unblock IP
python -c "from security.ip_tracker import IPTracker; t=IPTracker(); print('Blocked:', list(t.blocked.keys()))"
```
She does not invent answers. She confirms with this file, executes steps 1-5 per issue, and reports back exactly what the log says (`ATTEMPT` / `BLOCKED` / `ok`).

---

## Integration Notes
- `security/ip_tracker.py` and `security/sanitize_input.py` must be imported by `main.py` (add import at top)
- `security/security_events.log` — create directory if it doesn't exist (`os.makedirs` handled by tracker and sanitize)
- This file (`security/support_playbook.md`) — reference it when responding to any security-related customer report
- No secrets in this file — only procedure, no keys, no `.env` content
