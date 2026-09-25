# BRUCE AI CLOUD CONSOLE — Architecture Spec

Status: NAVIGATIONAL SLUGS ONLY. Not the local :9001 provider console.
Purpose: Billing + site routing layer. Vendor supply handled separately.

## Slug Map (all navigational — clients routed to actual sites)
- /sites/scan-tool → navigational slug
- /sites/hybrid → navigational slug
- /sites/ev → navigational slug
- /sites/diesel-commonrail → navigational slug
- /sites/automatic-transmission → navigational slug
- /sites/hydraulic-systems → navigational slug
- /sites/pneumatic-systems → navigational slug
- /sites/mechatronics → navigational slug

## Billing (prepaid, weekly/monthly/yearly)
- Stripe webhook handles checkout
- User gets single API key after payment
- No auth complexity — single key per user

## Vendor Supply
- Vendor agreements handled separately by user (not spoofed)
- Supply feeds into console routing, not reverse-engineered

## No Local Integration
- Separate from provider-console (:9001) and Groq bridge (:8080)
- Console can run independently at :9000 or hosted

## Security
- Stripe keys in .env only
- No OpenCode/Groq/OpenRouter keys in console (vendor-supplied)
- No secrets in chat — ever
