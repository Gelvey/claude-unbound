#!/bin/bash
# Quick verification script for Freebuff2API fixes
# Run this to verify the Docker status detection is working correctly

set -e

echo "🔍 Freebuff2API Fix Verification"
echo "================================"
echo ""

# Check if Docker is available
echo "1️⃣  Checking Docker availability..."
if command -v docker &> /dev/null; then
    echo "   ✅ Docker is installed"
    docker info --format '{{.ServerVersion}}' 2>/dev/null && echo "   ✅ Docker daemon is running" || echo "   ⚠️  Docker daemon may not be running"
else
    echo "   ❌ Docker not found in PATH"
fi
echo ""

# Check for freebuff2api container
echo "2️⃣  Checking freebuff2api container..."
CONTAINER_ID=$(docker ps -a --filter name=freebuff2api --format '{{.ID}}' 2>/dev/null || echo "")
if [ -n "$CONTAINER_ID" ]; then
    CONTAINER_STATUS=$(docker inspect --format '{{.State.Status}}' freebuff2api 2>/dev/null || echo "unknown")
    CONTAINER_RUNNING=$(docker inspect --format '{{.State.Running}}' freebuff2api 2>/dev/null || echo "false")
    echo "   ✅ Container exists: ${CONTAINER_ID:0:12}"
    echo "   📊 Status: $CONTAINER_STATUS"
    echo "   🏃 Running: $CONTAINER_RUNNING"
else
    echo "   ℹ️  No container named 'freebuff2api' found"
fi
echo ""

# Check Docker permissions
echo "3️⃣  Checking Docker permissions..."
if docker info &> /dev/null; then
    echo "   ✅ Can run Docker without sudo"
else
    if sudo -n docker info &> /dev/null 2>&1; then
        echo "   ⚠️  Docker requires sudo (passwordless sudo available)"
        echo "   💡 Fix: sudo usermod -aG docker $USER && newgrp docker"
    else
        echo "   ❌ Docker permission denied (sudo may require password)"
        echo "   💡 Fix: sudo usermod -aG docker $USER && log out/in"
    fi
fi
echo ""

# Check if port 8080 is in use
echo "4️⃣  Checking port 8080..."
if command -v lsof &> /dev/null; then
    PORT_USER=$(lsof -ti :8080 2>/dev/null | head -1 || echo "")
    if [ -n "$PORT_USER" ]; then
        echo "   ⚠️  Port 8080 is in use by PID $PORT_USER"
    else
        echo "   ✅ Port 8080 is available"
    fi
else
    echo "   ℹ️  lsof not available, skipping port check"
fi
echo ""

# Check credentials file
echo "5️⃣  Checking Freebuff credentials..."
CRED_FILE="$HOME/.config/manicode/credentials.json"
if [ -f "$CRED_FILE" ]; then
    PROFILE_COUNT=$(jq '.profiles | length' "$CRED_FILE" 2>/dev/null || echo "0")
    echo "   ✅ Credentials file exists"
    echo "   👤 Profiles found: $PROFILE_COUNT"
else
    echo "   ⚠️  Credentials file not found at: $CRED_FILE"
    echo "   💡 Setup: npm i -g freebuff && freebuff"
fi
echo ""

# Summary
echo "📋 Summary"
echo "=========="
if [ -n "$CONTAINER_ID" ] && [ "$CONTAINER_RUNNING" = "true" ]; then
    echo "🟢 Freebuff2API is running and healthy"
elif [ -n "$CONTAINER_ID" ]; then
    echo "🟡 Freebuff2API container exists but is stopped"
    echo "   💡 Start it via admin panel or: docker start freebuff2api"
else
    echo "⚪ Freebuff2API is not running"
    echo "   💡 Start it via admin panel's Freebuff tab"
fi
echo ""
echo "📖 For troubleshooting, see: docs/FREEBUFF_TROUBLESHOOTING.md"
echo ""
