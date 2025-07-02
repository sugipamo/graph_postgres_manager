.PHONY: help test test-unit test-integration test-all test-env-up test-env-down test-env-logs clean lint format

# Default target
help:
	@echo "Available commands:"
	@echo "  make test-env-up      - Start test environment (Neo4j + PostgreSQL)"
	@echo "  make test-env-down    - Stop test environment"
	@echo "  make test-env-logs    - Show test environment logs"
	@echo "  make test-unit        - Run unit tests"
	@echo "  make test-integration - Run integration tests"
	@echo "  make test-all         - Run all tests"
	@echo "  make test             - Run all tests with environment setup"
	@echo "  make lint             - Run code linting"
	@echo "  make format           - Format code"
	@echo "  make clean            - Clean up temporary files"

# Test environment management
test-env-up:
	@echo "Starting test environment..."
	docker-compose up -d neo4j postgres
	@echo "Waiting for services to be healthy..."
	@timeout=60; \
	while [ $$timeout -gt 0 ]; do \
		if docker-compose ps | grep -q "healthy"; then \
			echo "Services are healthy!"; \
			break; \
		fi; \
		echo "Waiting for services... ($$timeout seconds remaining)"; \
		sleep 5; \
		timeout=$$((timeout - 5)); \
	done; \
	if [ $$timeout -eq 0 ]; then \
		echo "Timeout waiting for services to be healthy"; \
		exit 1; \
	fi

test-env-down:
	@echo "Stopping test environment..."
	docker-compose down -v

test-env-logs:
	docker-compose logs -f

# Testing
test-unit:
	@echo "Running unit tests..."
	python -m pytest tests/ -v --ignore=tests/integration/

test-integration: test-env-up
	@echo "Running integration tests..."
	docker-compose run --rm app python -m pytest tests/integration/ -v

test-all: test-unit test-integration

test: test-env-up
	@echo "Running all tests..."
	docker-compose run --rm app python -m pytest tests/ -v
	@make test-env-down

# Code quality
lint:
	@echo "Running linting..."
	docker-compose run --rm app ruff check src/ tests/

format:
	@echo "Formatting code..."
	docker-compose run --rm app ruff format src/ tests/

# Clean up
clean:
	@echo "Cleaning up..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

# Development helpers
shell:
	docker-compose run --rm app /bin/bash

python-shell:
	docker-compose run --rm app python

# Build
build:
	docker-compose build

rebuild:
	docker-compose build --no-cache