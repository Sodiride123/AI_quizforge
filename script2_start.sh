#!/bin/bash
# Script 2: Start the app via supervisord
set -e

APP_DIR="/workspace/AI_quizforge"
CONF="$APP_DIR/_superninja_startup.conf"

# Copy config to supervisord
cp "$CONF" /etc/supervisor/conf.d/quizforge.conf
supervisorctl reread
supervisorctl update

echo "App started on port 8085."
echo ""
echo "Commands:"
echo "  supervisorctl status quizforge_server    # check status"
echo "  supervisorctl restart quizforge_server   # restart"
echo "  supervisorctl stop quizforge_server      # stop"
echo "  supervisorctl start quizforge_server     # start"
