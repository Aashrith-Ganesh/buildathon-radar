# macOS Launchd Scheduling Guide for Buildathon Radar

This directory contains native macOS `launchd` configuration files replacing Linux systemd.

## Services

1. **`com.buildathon.radar.plist`**
   - **Type:** Hourly interval timer
   - **Schedule:** On load and then hourly while the user LaunchAgent is active
   - **Command:** `venv/bin/python main.py`
   - **Working Directory:** `/Users/aashrith/Projects/buildathon-radar`
   - **Logs:** `logs/radar.log` and `logs/radar_error.log`

2. **`com.buildathon.tracker.plist`**
   - **Type:** Background KeepAlive daemon
   - **Service:** FastAPI tracker server on `http://127.0.0.1:8015`
   - **Command:** `venv/bin/uvicorn buildathon_radar.tracker_service:app --host 127.0.0.1 --port 8015`
   - **Logs:** `logs/tracker.log` and `logs/tracker_error.log`

## Management Script

Use `./scripts/manage_launchd.sh`:

```bash
# 1. Validate plist syntax
./scripts/manage_launchd.sh validate

# 2. Install plists to ~/Library/LaunchAgents/
./scripts/manage_launchd.sh install

# 3. Start services (only with user approval)
./scripts/manage_launchd.sh start-tracker
./scripts/manage_launchd.sh start-radar

# 4. Check status
./scripts/manage_launchd.sh status

# 5. Stop services
./scripts/manage_launchd.sh stop-tracker
./scripts/manage_launchd.sh stop-radar

# 6. View logs
./scripts/manage_launchd.sh logs
```

## Manual Commands

```bash
# Validate plists
plutil -lint scheduler/launchd/com.buildathon.radar.plist
plutil -lint scheduler/launchd/com.buildathon.tracker.plist

# Install manually
cp scheduler/launchd/*.plist ~/Library/LaunchAgents/

# Load / Unload
launchctl load -w ~/Library/LaunchAgents/com.buildathon.radar.plist
launchctl unload ~/Library/LaunchAgents/com.buildathon.radar.plist
```

To configure the interval, change `StartInterval` in the installed
`~/Library/LaunchAgents/com.buildathon.radar.plist` (seconds), then run
`scripts/manage_launchd.sh start-radar` to reload that installed agent. The
checked-in default is 3600 seconds.
