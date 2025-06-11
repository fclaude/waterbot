# WaterBot - Makefile for development automation
.PHONY: help install install-dev test test-cov lint format type-check security-check clean build run docker-build docker-run setup-dev check-all

# Default target
.DEFAULT_GOAL := help

# Configuration
PYTHON := python3
PIP := pip3
PYTEST := pytest
FLAKE8 := flake8
BLACK := black
ISORT := isort
MYPY := mypy
BANDIT := bandit
SAFETY := safety
DOCKER_IMAGE := waterbot
DOCKER_TAG := latest

help: ## Show this help message
	@echo "WaterBot Development Commands"
	@echo "============================"
	@echo
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "Environment Variables:"
	@echo "  PYTHON   - Python executable (default: python3)"
	@echo "  PIP      - Pip executable (default: pip3)"

# Installation targets
install: ## Install production dependencies
	$(PIP) install -r requirements.txt

install-dev: ## Install development dependencies
	$(PIP) install -r requirements.txt
	$(PIP) install black flake8 isort mypy bandit safety pre-commit
	pre-commit install

setup-dev: install-dev ## Setup complete development environment
	@echo "Creating .env file from template..."
	@if [ ! -f .env ]; then cp env.sample .env; fi
	@echo "Development environment setup complete!"
	@echo "Please edit .env file with your configuration."

# Testing targets
test: ## Run unit tests
	$(PYTEST) tests/ -v

test-cov: ## Run tests with coverage report
	$(PYTEST) tests/ -v --cov=waterbot --cov-report=html --cov-report=term-missing

test-cov-fail: ## Run tests with coverage and fail if below threshold
	$(PYTEST) tests/ -v --cov=waterbot --cov-report=html --cov-report=term-missing --cov-fail-under=80

test-fast: ## Run tests with minimal output
	$(PYTEST) tests/ -q

test-watch: ## Run tests in watch mode (requires pytest-watch)
	ptw tests/ waterbot/

# Code quality targets
lint: ## Run linting checks
	$(FLAKE8) waterbot/ tests/ --max-line-length=88 --extend-ignore=E203,W503

format: ## Format code with black and isort
	$(BLACK) waterbot/ tests/ --line-length=88
	$(ISORT) waterbot/ tests/ --profile=black

format-check: ## Check if code formatting is correct
	$(BLACK) waterbot/ tests/ --line-length=88 --check
	$(ISORT) waterbot/ tests/ --profile=black --check-only

type-check: ## Run type checking with mypy
	$(MYPY) waterbot/ --ignore-missing-imports --no-strict-optional

security-check: ## Run security checks
	$(BANDIT) -r waterbot/ -f json -o bandit-report.json || true
	$(BANDIT) -r waterbot/ -f txt
	$(SAFETY) check --json --output safety-report.json || true
	$(SAFETY) check

# Combined quality checks
check-all: lint format-check type-check security-check test-cov-fail ## Run all quality checks

# Application targets
run: ## Run the waterbot application
	$(PYTHON) -m waterbot.bot

run-emulation: ## Run waterbot in emulation mode
	OPERATION_MODE=emulation $(PYTHON) -m waterbot.bot

run-test-command: ## Test basic command parsing
	$(PYTHON) -c "from waterbot.utils.command_parser import parse_command; print(parse_command('status'))"

# Build targets
build: clean ## Build the package
	$(PYTHON) setup.py sdist bdist_wheel

install-local: ## Install package locally in development mode
	$(PIP) install -e .

# Docker targets
docker-build: ## Build Docker image
	docker build -t $(DOCKER_IMAGE):$(DOCKER_TAG) .

docker-run: ## Run Docker container
	docker run -it --rm --env-file .env $(DOCKER_IMAGE):$(DOCKER_TAG)

docker-run-emulation: ## Run Docker container in emulation mode
	docker run -it --rm -e OPERATION_MODE=emulation $(DOCKER_IMAGE):$(DOCKER_TAG)

# Cleanup targets
clean: ## Clean build artifacts
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf .mypy_cache/
	rm -f bandit-report.json
	rm -f safety-report.json
	find . -path ./.venv -prune -o -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -path ./.venv -prune -o -type f -name "*.pyc" -exec rm -f {} + 2>/dev/null || true

clean-all: clean ## Clean all generated files including logs and schedules
	rm -f *.log
	rm -f schedules.json

# Development utilities
deps-update: ## Update all dependencies to latest versions
	$(PIP) list --outdated --format=freeze | grep -v '^\-e' | cut -d = -f 1 | xargs -n1 $(PIP) install -U

deps-tree: ## Show dependency tree
	pipdeptree

requirements-update: ## Update requirements.txt with current environment
	$(PIP) freeze > requirements.txt

# Git hooks
pre-commit-install: ## Install pre-commit hooks
	pre-commit install

pre-commit-run: ## Run pre-commit on all files
	pre-commit run --all-files

# Documentation
docs-serve: ## Serve documentation locally (if you add docs later)
	@echo "Documentation serving not implemented yet"
	@echo "README.md contains current documentation"

# Development workflow
dev-check: format lint type-check test ## Quick development check
	@echo "✅ Development checks passed!"

ci-check: check-all ## Full CI/CD checks
	@echo "✅ CI/CD checks passed!"

# Release helpers
version: ## Show current version
	@$(PYTHON) setup.py --version

bump-version: ## Show instructions for version bumping
	@echo "To bump version:"
	@echo "1. Edit setup.py version"
	@echo "2. Run: git tag v<version>"
	@echo "3. Run: git push origin v<version>"

# Monitoring and debugging
logs: ## Show recent logs
	tail -f waterbot.log 2>/dev/null || echo "No log file found"

status: ## Show application status
	@echo "Checking WaterBot status..."
	@if pgrep -f "waterbot.bot" > /dev/null; then \
		echo "✅ WaterBot is running"; \
		pgrep -f "waterbot.bot" | head -1 | xargs ps -p; \
	else \
		echo "❌ WaterBot is not running"; \
	fi

# System requirements check
check-deps: ## Check if required system dependencies are installed
	@echo "Checking system dependencies..."
	@command -v $(PYTHON) >/dev/null 2>&1 || { echo "❌ Python 3 is required but not installed"; exit 1; }
	@command -v signal-cli >/dev/null 2>&1 || echo "⚠️  signal-cli not found - required for Signal integration"
	@echo "✅ Basic dependencies check passed"

# Environment info
env-info: ## Show environment information
	@echo "Environment Information:"
	@echo "======================="
	@echo "Python: $$($(PYTHON) --version)"
	@echo "Pip: $$($(PIP) --version)"
	@echo "Working directory: $$(pwd)"
	@echo "Git branch: $$(git branch --show-current 2>/dev/null || echo 'Not a git repo')"
	@echo "Git commit: $$(git rev-parse --short HEAD 2>/dev/null || echo 'Not a git repo')"
	@if [ -f .env ]; then echo "✅ .env file exists"; else echo "❌ .env file missing"; fi
