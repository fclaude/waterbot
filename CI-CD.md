# CI/CD Pipeline Documentation

WaterBot includes comprehensive CI/CD pipeline configurations for both GitLab and GitHub, ensuring code quality and automated testing on every commit.

## Pipeline Overview

### Stages
1. **Quality** - Code formatting, linting, type checking, security scanning
2. **Test** - Unit tests across multiple Python versions with coverage
3. **Build** - Package building and Docker image creation
4. **Deploy** - Automated deployment (when configured)

### Quality Gates
- ✅ All tests must pass
- ✅ Code coverage ≥80%
- ✅ No linting errors
- ✅ Proper code formatting
- ✅ Security vulnerability scanning

## GitLab CI/CD

### Configuration Files
- `.gitlab-ci.yml` - Simplified, robust pipeline (recommended)
- `.gitlab-ci-full.yml` - Comprehensive pipeline with all features

### Jobs
- `code-quality` - Formatting, linting, type checking, security
- `test-unit` - Unit tests with coverage reporting
- `test-python-versions` - Multi-version Python testing (3.8-3.11)
- `build-package` - Python package building
- `build-docker` - Docker image building and testing
- `mr-check` - Comprehensive checks for merge requests

### Usage
```bash
# The pipeline runs automatically on:
# - Pushes to main branch
# - Merge requests
# - Git tags

# Manual pipeline trigger
# Go to CI/CD > Pipelines > Run Pipeline
```

### Artifacts
- Coverage reports (HTML format)
- Built packages (dist/)
- Security scan reports

## GitHub Actions

### Configuration
- `.github/workflows/ci.yml` - Complete CI/CD workflow

### Jobs
- `quality` - Code quality checks
- `test` - Multi-version testing with coverage
- `docker` - Docker build and test
- `build` - Package building
- `release` - Automated release to PyPI (on tags)

### Usage
```bash
# The workflow runs automatically on:
# - Pushes to main branch
# - Pull requests
# - Releases

# Manual workflow dispatch
# Go to Actions > CI/CD > Run workflow
```

### Features
- Codecov integration for coverage reporting
- Automatic PyPI publishing on releases
- Multi-platform Docker builds
- Artifact upload and download

## Local CI/CD Simulation

### Full Pipeline Simulation
```bash
# Run complete CI/CD checks locally
make ci-check

# Quick development checks
make dev-check

# Individual components
make format-check
make lint
make type-check
make security-check
make test-cov
```

### Docker Testing
```bash
# Test Docker build locally
make docker-build
make docker-run-emulation

# Use docker-compose profiles
docker-compose --profile test up
docker-compose --profile lint up
```

## Configuration Details

### Environment Variables
Both pipelines use these key variables:
- `OPERATION_MODE=emulation` - Ensures hardware-independent testing
- `PIP_CACHE_DIR` - Speeds up builds with dependency caching
- `PYTHONPATH` - Ensures proper module resolution

### Caching
- **GitLab**: Pip cache and virtual environment caching
- **GitHub**: Built-in pip caching with actions/setup-python

### Matrix Testing
Both platforms test across Python versions:
- Python 3.8
- Python 3.9
- Python 3.10
- Python 3.11

## Security Scanning

### Tools Used
- **Bandit** - Python security vulnerability scanner
- **Safety** - Dependency vulnerability checker
- **GitLab Security Templates** - SAST and dependency scanning (full version)

### Reports
Security scan results are stored as artifacts:
- `bandit-report.json` - Code security issues
- `safety-report.json` - Dependency vulnerabilities

## Deployment

### GitLab Deployment
The full pipeline includes deployment stages:
- **Staging** - Manual deployment to staging environment
- **Production** - Manual deployment on tags only

### GitHub Deployment
- **PyPI Publishing** - Automatic on releases with proper secrets
- **Docker Registry** - Can be configured with registry secrets

## Troubleshooting

### Common Issues

#### 1. Missing Templates (GitLab)
**Error**: `Included file 'Security/License-Scanning.gitlab-ci.yml' is empty or does not exist!`

**Solution**: Use the simplified `.gitlab-ci.yml` (already configured)

#### 2. Registry Authentication (GitLab)
**Error**: Docker registry login failures

**Solution**: The simplified pipeline avoids registry push, or configure:
```bash
# GitLab CI/CD Variables
CI_REGISTRY_USER: your-username
CI_REGISTRY_PASSWORD: your-password
CI_REGISTRY_IMAGE: your-registry/waterbot
```

#### 3. PyPI Publishing (GitHub)
**Error**: Authentication failed for PyPI

**Solution**: Add PyPI API token to GitHub secrets:
```bash
# GitHub Repository Secrets
PYPI_API_TOKEN: your-pypi-token
```

#### 4. Coverage Reporting
**Error**: Coverage format issues

**Solution**: The simplified pipelines use basic HTML coverage reports

### Debug Tips

#### Local Debugging
```bash
# Test the exact commands used in CI
source .venv/bin/activate
make format-check
make lint
make test-cov

# Check Docker build
docker build -t waterbot:test .
docker run --rm waterbot:test python -c "import waterbot; print('OK')"
```

#### Pipeline Variables
Check these in your CI/CD environment:
- Python version and location
- Virtual environment activation
- Environment variables
- File permissions

## Best Practices

### For Contributors
1. **Run local checks before pushing**:
   ```bash
   make dev-check
   ```

2. **Test across Python versions locally**:
   ```bash
   pyenv install 3.8.18 3.9.18 3.10.13 3.11.10
   for version in 3.8.18 3.9.18 3.10.13 3.11.10; do
     pyenv shell $version
     make test
   done
   ```

3. **Check Docker builds**:
   ```bash
   make docker-build
   ```

### For Maintainers
1. **Monitor pipeline performance** - Optimize slow jobs
2. **Update dependencies regularly** - Keep security tools current
3. **Review security reports** - Address vulnerabilities promptly
4. **Maintain quality gates** - Don't lower standards

## Pipeline Monitoring

### GitLab
- **CI/CD > Pipelines** - View pipeline status and history
- **CI/CD > Jobs** - Detailed job logs and artifacts
- **Security & Compliance** - Security scan results

### GitHub
- **Actions** - Workflow runs and status
- **Insights > Dependency graph** - Security advisories
- **Settings > Secrets** - Manage deployment credentials

## Extending the Pipeline

### Adding New Jobs
1. Follow the existing pattern in `.gitlab-ci.yml` or `.github/workflows/ci.yml`
2. Use appropriate stage and dependencies
3. Include proper artifacts and caching
4. Test locally first with `make` commands

### Custom Deployment
1. Add deployment scripts to `scripts/` directory
2. Create new pipeline jobs for your target environment
3. Use manual triggers for production deployments
4. Include proper secret management

---

For pipeline issues or improvements, please open an issue in the repository.