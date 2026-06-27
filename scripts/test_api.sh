#!/bin/bash
# Quick API tests (run after: docker compose up -d)
set -e

BASE=${1:-http://localhost:8001}
echo "Testing API at $BASE"

echo -e "\n1. Root"
curl -s "$BASE/" | head -5

echo -e "\n\n2. Health"
curl -s "$BASE/api/health"

echo -e "\n\n3. Models"
curl -s -H "Authorization: Bearer ${OPENROUTER_API_KEY:-test}" "$BASE/v1/models" | head -5

echo -e "\n\nDone."
