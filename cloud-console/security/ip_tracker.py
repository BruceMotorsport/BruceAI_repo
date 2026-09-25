#!/usr/bin/env python3
"""
IP Tracker + Auto-Block — Security layer for Bruce AI Cloud Console.
Tracks failed auth, honeypot hits, injection attempts per IP.
Block after 3 violations within 60 minutes.
"""
import json, os, time
from datetime import datetime, timedelta
from collections import defaultdict

IP_LOG_FILE = os.path.join(os.path.dirname(__file__), "security", "ip_blocks.json")
MAX_ATTEMPTS = 3
BLOCK_DURATION_MIN = 60

class IPTracker:
    def __init__(self):
        os.makedirs(os.path.dirname(IP_LOG_FILE) or ".", exist_ok=True)
        self.load()

    def load(self):
        try:
            with open(IP_LOG_FILE) as f:
                self.attempts = defaultdict(list)  # ip -> [timestamps]
                self.blocked = {}  # ip -> block_expiry
                data = json.load(f)
                # Parse stored attempts
                for ip, entries in data.get("attempts", {}).items():
                    self.attempts[ip] = [datetime.fromisoformat(ts) for ts in entries]
                for ip, ts in data.get("blocked", {}).items():
                    self.blocked[ip] = datetime.fromisoformat(ts) if isinstance(ts, str) else ts
        except (FileNotFoundError, json.JSONDecodeError):
            self.attempts = defaultdict(list)
            self.blocked = {}

    def save(self):
        # Clean expired attempts first
        now = datetime.utcnow()
        for ip in list(self.attempts):
            self.attempts[ip] = [t for t in self.attempts[ip] if now - t < timedelta(minutes=BLOCK_DURATION_MIN)]
            if not self.attempts[ip]:
                del self.attempts[ip]
        # Clean expired blocks
        for ip in list(self.blocked):
            if self.blocked[ip] < now:
                del self.blocked[ip]
        data = {
            "attempts": {ip: [t.isoformat() for t in times] for ip, times in self.attempts.items()},
            "blocked": {ip: t.isoformat() for ip, t in self.blocked.items()}
        }
        with open(IP_LOG_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def is_blocked(self, ip: str) -> bool:
        self.load()
        now = datetime.utcnow()
        # Clear old blocks
        self.blocked = {k: v for k, v in self.blocked.items() if v > now}
        return ip in self.blocked

    def log_attempt(self, ip: str, endpoint: str, api_key_hash: str = "unknown"):
        self.load()
        now = datetime.utcnow()
        # Add attempt
        self.attempts.setdefault(ip, []).append(now)
        # Keep only attempts within BLOCK_DURATION_MIN
        self.attempts[ip] = [t for t in self.attempts[ip] if now - t < timedelta(minutes=BLOCK_DURATION_MIN)]
        # Check if blocked
        count = len(self.attempts[ip])
        if count >= MAX_ATTEMPTS:
            self.blocked[ip] = now + timedelta(minutes=BLOCK_DURATION_MIN)
            # Security log
            with open(os.path.join(os.path.dirname(__file__), "security", "security_events.log"), "a") as log:
                log.write(f"{now.isoformat()} | BLOCKED | ip={ip} | endpoint={endpoint} | attempts={count} | key={api_key_hash}\n")
        else:
            with open(os.path.join(os.path.dirname(__file__), "security", "security_events.log"), "a") as log:
                log.write(f"{now.isoformat()} | ATTEMPT | ip={ip} | endpoint={endpoint} | attempts={count} | key={api_key_hash}\n")
        self.save()
        return count >= MAX_ATTEMPTS

if __name__ == "__main__":
    # Test mode
    tracker = IPTracker()
    print(f"Blocked IPs: {list(tracker.blocked.keys())}")
    print(f"Active attempts: {dict((k, len(v)) for k, v in tracker.attempts.items())}")
