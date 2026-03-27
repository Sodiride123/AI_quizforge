#!/bin/bash
# Script 2: Start/restart the app via supervisord
set -e

APP_DIR="/workspace/AI_quizforge"
CONF="$APP_DIR/_superninja_startup.conf"

# Ensure supervisord config is in place
cp "$CONF" /etc/supervisor/conf.d/quizforge.conf
supervisorctl reread
supervisorctl update

# If already running, restart; otherwise start
if supervisorctl status quizforge_server 2>/dev/null | grep -q RUNNING; then
    supervisorctl restart quizforge_server
    echo "App restarted on port 8085."
else
    supervisorctl start quizforge_server 2>/dev/null || true
    echo "App started on port 8085."
fi

echo ""
echo "Commands:"
echo "  supervisorctl status quizforge_server    # check status"
echo "  supervisorctl restart quizforge_server   # restart"
echo "  supervisorctl stop quizforge_server      # stop"
echo "  supervisorctl start quizforge_server     # start"
