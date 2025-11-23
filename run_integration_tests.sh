#!/bin/bash
# Integration test runner script

set -e

echo "🚀 Starting integration test environment..."

# Start test services
docker-compose -f docker-compose.test.yml up -d

# Wait for services to be healthy
echo "⏳ Waiting for Redis..."
timeout=60
while ! docker-compose -f docker-compose.test.yml exec -T redis redis-cli ping | grep -q PONG; do
    if [ $timeout -le 0 ]; then
        echo "❌ Redis failed to start"
        exit 1
    fi
    sleep 2
    timeout=$((timeout - 2))
done

echo "⏳ Waiting for Qdrant..."
timeout=120
while ! curl -f http://localhost:6333/ > /dev/null 2>&1; do
    if [ $timeout -le 0 ]; then
        echo "❌ Qdrant failed to start"
        exit 1
    fi
    sleep 5
    timeout=$((timeout - 5))
done

echo "✅ Services are ready!"

# Set environment variables for integration tests
export REDIS_URL="redis://localhost:6379/0"
export QDRANT_URL="http://localhost:6333"
export QDRANT_API_KEY=""

# Run integration tests
echo "🧪 Running integration tests..."
python -m pytest tests/test_integration.py -m integration -v --tb=short

# Cleanup
echo "🧹 Cleaning up..."
docker-compose -f docker-compose.test.yml down -v

echo "✅ Integration tests completed!"