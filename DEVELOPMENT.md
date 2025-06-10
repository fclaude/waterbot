# WaterBot Development Guide

This guide covers development setup, workflows, and best practices for contributing to WaterBot.

## Quick Start

### Option 1: Automated Setup
```bash
# Run the setup script
chmod +x scripts/setup-dev.sh
./scripts/setup-dev.sh
```

### Option 2: Manual Setup
```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
make install-dev

# Create environment file
cp env.sample .env
# Edit .env with your configuration

# Setup pre-commit hooks
pre-commit install

# Run tests to verify setup
make test
```

### Option 3: Docker Development
```bash
# Build and run development container
docker-compose --profile dev up waterbot-dev

# Run tests in container
docker-compose --profile test up waterbot-test

# Run linting
docker-compose --profile lint up waterbot-lint
```

## Development Workflow

### 1. Code Quality Checks

All code must pass quality checks before being merged:

```bash
# Format code
make format

# Check formatting
make format-check

# Run linting
make lint

# Type checking
make type-check

# Security checks
make security-check

# Run all quality checks
make check-all
```

### 2. Testing

Comprehensive testing is required:

```bash
# Run unit tests
make test

# Run tests with coverage
make test-cov

# Run tests and fail if coverage is below threshold
make test-cov-fail

# Run tests in watch mode (requires pytest-watch)
make test-watch

# Run fast tests only
make test-fast
```

### 3. Running the Application

```bash
# Run in emulation mode (no hardware required)
make run-emulation

# Run in production mode (requires Raspberry Pi)
make run

# Test command parsing
make run-test-command
```

## Available Make Commands

Run `make help` to see all available commands:

- **Installation**: `install`, `install-dev`, `setup-dev`
- **Testing**: `test`, `test-cov`, `test-cov-fail`, `test-fast`, `test-watch`
- **Code Quality**: `lint`, `format`, `format-check`, `type-check`, `security-check`
- **Application**: `run`, `run-emulation`, `run-test-command`
- **Build**: `build`, `install-local`
- **Docker**: `docker-build`, `docker-run`, `docker-run-emulation`
- **Cleanup**: `clean`, `clean-all`
- **Development**: `dev-check`, `ci-check`, `check-all`

## Project Structure

```
waterbot/
├── waterbot/                 # Main package
│   ├── __init__.py
│   ├── bot.py               # Main application entry point
│   ├── config.py            # Configuration management
│   ├── scheduler.py         # Device scheduling
│   ├── gpio/                # GPIO control modules
│   │   ├── __init__.py
│   │   ├── handler.py       # Device controller
│   │   └── interface.py     # GPIO interfaces (hardware/mock)
│   ├── signal/              # Signal integration
│   │   ├── __init__.py
│   │   └── bot.py           # Signal bot implementation
│   └── utils/               # Utilities
│       ├── __init__.py
│       └── command_parser.py # Command parsing logic
├── tests/                   # Test suite
│   ├── test_*.py           # Unit tests
│   └── __init__.py
├── scripts/                 # Development scripts
├── data/                    # Runtime data (schedules, etc.)
├── logs/                    # Log files
├── .gitlab-ci.yml          # CI/CD pipeline
├── docker-compose.yml      # Docker development setup
├── Dockerfile              # Container image
├── Makefile                # Development automation
├── pyproject.toml          # Modern Python configuration
├── requirements.txt        # Dependencies
└── README.md               # User documentation
```

## Architecture Overview

### Core Components

1. **Bot Module** (`waterbot/bot.py`)
   - Main application entry point
   - Coordinates scheduler and Signal bot
   - Handles graceful shutdown

2. **GPIO Handler** (`waterbot/gpio/handler.py`)
   - Manages device state and operations
   - Handles timing and scheduling
   - Provides hardware abstraction

3. **Scheduler** (`waterbot/scheduler.py`)
   - Time-based device control
   - Schedule persistence and management
   - Integration with GPIO handler

4. **Signal Bot** (`waterbot/signal/bot.py`)
   - Signal message processing
   - Command execution
   - Response generation

5. **Configuration** (`waterbot/config.py`)
   - Environment variable management
   - Schedule configuration
   - Device mapping

### Design Principles

- **Dependency Injection**: All components accept their dependencies for easy testing
- **Interface Segregation**: GPIO operations abstracted behind interfaces
- **Single Responsibility**: Each module has a clear, focused purpose
- **Testability**: All code designed to be easily unit tested

## Testing Strategy

### Test Categories

1. **Unit Tests**: Test individual components in isolation
2. **Integration Tests**: Test component interactions
3. **Hardware Simulation**: Test GPIO operations without hardware

### Test Organization

- `test_gpio_interface.py`: GPIO interface implementations
- `test_gpio_handler.py`: Device controller logic
- `test_config.py`: Configuration management
- `test_scheduler.py`: Scheduling functionality
- `test_signal_bot.py`: Signal bot integration
- `test_command_parser.py`: Command parsing logic

### Testing Best Practices

- Use dependency injection for testability
- Mock external dependencies (hardware, network)
- Test edge cases and error conditions
- Maintain high test coverage (>80%)
- Use descriptive test names and docstrings

## Code Style Guidelines

### Python Style

- Follow PEP 8 with 88-character line length
- Use Black for automatic formatting
- Sort imports with isort
- Use type hints for all public APIs
- Write comprehensive docstrings

### Git Workflow

1. Create feature branch from main
2. Write tests for new functionality
3. Implement feature with proper error handling
4. Ensure all quality checks pass
5. Create merge request with description
6. Address review feedback
7. Merge after approval

### Commit Messages

Follow conventional commit format:

```
type(scope): description

body (optional)

footer (optional)
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Examples:
- `feat(scheduler): add daily recurring schedules`
- `fix(gpio): handle device not found error`
- `docs(readme): update installation instructions`

## CI/CD Pipeline

The GitLab CI/CD pipeline runs on every commit and includes:

### Stages

1. **Prepare**: Install dependencies
2. **Quality**: Code formatting, linting, type checking
3. **Test**: Unit tests with coverage across Python versions
4. **Security**: Security scanning (Bandit, Safety)
5. **Build**: Package building and Docker image creation
6. **Deploy**: Deployment to staging/production (manual)

### Quality Gates

- All tests must pass
- Code coverage must be ≥80%
- No linting errors
- No security vulnerabilities (high severity)
- Code must be properly formatted

## Docker Development

### Development Container

```bash
# Start development environment
docker-compose --profile dev up

# Run specific services
docker-compose --profile test up waterbot-test
docker-compose --profile lint up waterbot-lint
```

### Production Container

```bash
# Build production image
make docker-build

# Run production container
make docker-run
```

## Configuration Management

### Environment Variables

All configuration via environment variables or `.env` file:

- `OPERATION_MODE`: `rpi` or `emulation`
- `SIGNAL_PHONE_NUMBER`: Bot's Signal phone number
- `SIGNAL_GROUP_ID`: Target Signal group ID
- `ENABLE_SCHEDULING`: Enable/disable scheduling
- `LOG_LEVEL`: Logging level

### Device Configuration

Map devices to GPIO pins:

```bash
DEVICE_PUMP=17
DEVICE_LIGHT=18
DEVICE_FAN=27
```

### Schedule Configuration

Two options:
1. Environment variables: `SCHEDULE_PUMP_ON=08:00,20:00`
2. JSON file: `schedules.json`

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure virtual environment is activated
2. **GPIO Errors**: Use emulation mode for development
3. **Signal CLI Issues**: Verify signal-cli installation and registration
4. **Permission Errors**: Check file permissions and user access
5. **Test Failures**: Check mock configuration and dependencies

### Debug Mode

Enable debug logging:

```bash
export DEBUG_MODE=true
export LOG_LEVEL=DEBUG
make run-emulation
```

### Development Tools

- **Pre-commit**: Automatic quality checks before commits
- **pytest-watch**: Continuous testing during development
- **Coverage**: HTML coverage reports in `htmlcov/`
- **Type Checking**: MyPy for static type analysis

## Contributing

1. Fork the repository
2. Create a feature branch
3. Follow the development workflow
4. Ensure all quality checks pass
5. Submit a merge request with clear description
6. Respond to review feedback promptly

## Resources

- [Python Testing 101](https://realpython.com/python-testing/)
- [Docker for Development](https://docs.docker.com/develop/)
- [GitLab CI/CD](https://docs.gitlab.com/ee/ci/)
- [Pre-commit Hooks](https://pre-commit.com/)
- [Conventional Commits](https://www.conventionalcommits.org/)

---

For questions or support, please open an issue in the project repository.