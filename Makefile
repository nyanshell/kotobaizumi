.PHONY: help install install-dev format lint test test-cov clean setup-hooks run docker-build docker-run

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install package in editable mode
	pip install -e .

install-dev: ## Install development dependencies
	pip install -e .
	pip install -r requirements-dev.txt

setup-hooks: install-dev ## Setup pre-commit hooks
	pre-commit install

format: ## Format code with ruff
	ruff format .

lint: ## Lint code with ruff
	ruff check .

lint-fix: ## Lint and fix code with ruff
	ruff check --fix .

test: ## Run tests
	python -m pytest

test-cov: ## Run tests with coverage report
	python -m pytest --cov=app --cov-report=term-missing --cov-report=html

test-ci: ## Run tests for CI (with XML coverage)
	python -m pytest --cov=app --cov-report=xml --cov-report=term

clean: ## Clean up generated files
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf coverage.xml
	rm -rf .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

run-dev: ## Run development server with dotenv
	python -m dotenv run python app/app.py

run: ## Run production server
	python app/app.py

cli: ## Run CLI help
	python app/cli.py --help

user-create: ## Create a new user (usage: make user-create USER=username)
	python app/cli.py create $(USER)

user-list: ## List all users
	python app/cli.py list

docker-build: ## Build Docker image
	docker build . --progress=plain -t kotobaizumi:latest

docker-run: ## Run Docker container
	docker run --env-file=.env -p 5000:5000 -v ./data:/data -it kotobaizumi:latest

check: format lint test ## Run all checks (format, lint, test)

ci: lint test-ci ## Run CI checks
