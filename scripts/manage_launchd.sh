#!/bin/bash
# manage_launchd.sh - macOS launchd management script for Buildathon Radar

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
LOGS_DIR="$DIR/logs"

mkdir -p "$LOGS_DIR"
mkdir -p "$LAUNCH_AGENTS_DIR"

RADAR_PLIST="com.buildathon.radar.plist"
TRACKER_PLIST="com.buildathon.tracker.plist"

validate() {
    echo "=== Validating launchd plists with plutil ==="
    plutil -lint "$DIR/scheduler/launchd/$RADAR_PLIST"
    plutil -lint "$DIR/scheduler/launchd/$TRACKER_PLIST"
    echo "All plists are syntactically valid."
}

install() {
    validate
    echo "Copying plists to $LAUNCH_AGENTS_DIR..."
    cp "$DIR/scheduler/launchd/$RADAR_PLIST" "$LAUNCH_AGENTS_DIR/"
    cp "$DIR/scheduler/launchd/$TRACKER_PLIST" "$LAUNCH_AGENTS_DIR/"
    echo "Files installed to $LAUNCH_AGENTS_DIR."
    echo "Note: To activate jobs, run: $0 start-tracker or $0 start-radar"
}

start_tracker() {
    echo "Loading and starting tracker daemon..."
    launchctl unload "$LAUNCH_AGENTS_DIR/$TRACKER_PLIST" 2>/dev/null || true
    launchctl load -w "$LAUNCH_AGENTS_DIR/$TRACKER_PLIST"
    echo "Tracker started on http://127.0.0.1:8015"
}

stop_tracker() {
    echo "Stopping tracker daemon..."
    launchctl unload "$LAUNCH_AGENTS_DIR/$TRACKER_PLIST" 2>/dev/null || true
    echo "Tracker stopped."
}

start_radar() {
    echo "Loading hourly radar refresh..."
    launchctl unload "$LAUNCH_AGENTS_DIR/$RADAR_PLIST" 2>/dev/null || true
    launchctl load -w "$LAUNCH_AGENTS_DIR/$RADAR_PLIST"
    echo "Hourly radar timer loaded."
}

stop_radar() {
    echo "Unloading hourly radar refresh..."
    launchctl unload "$LAUNCH_AGENTS_DIR/$RADAR_PLIST" 2>/dev/null || true
    echo "Radar timer unloaded."
}

status() {
    echo "=== Launchd Service Status ==="
    echo "Tracker:"
    launchctl list | grep "com.buildathon.tracker" || echo "  com.buildathon.tracker: NOT LOADED"
    echo "Radar:"
    launchctl list | grep "com.buildathon.radar" || echo "  com.buildathon.radar: NOT LOADED"
}

logs() {
    echo "=== Recent Radar Logs ==="
    tail -n 20 "$LOGS_DIR/radar.log" 2>/dev/null || echo "No radar.log yet."
    echo "=== Recent Tracker Logs ==="
    tail -n 20 "$LOGS_DIR/tracker.log" 2>/dev/null || echo "No tracker.log yet."
}

case "$1" in
    validate)
        validate
        ;;
    install)
        install
        ;;
    start-tracker)
        start_tracker
        ;;
    stop-tracker)
        stop_tracker
        ;;
    start-radar)
        start_radar
        ;;
    stop-radar)
        stop_radar
        ;;
    start-all)
        start_tracker
        start_radar
        ;;
    stop-all)
        stop_tracker
        stop_radar
        ;;
    status)
        status
        ;;
    logs)
        logs
        ;;
    *)
        echo "Usage: $0 {validate|install|start-tracker|stop-tracker|start-radar|stop-radar|start-all|stop-all|status|logs}"
        exit 1
        ;;
esac
