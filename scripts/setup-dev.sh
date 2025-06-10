#!/bin/bash
# Development environment setup script for WaterBot

set -e

echo "🤖 WaterBot Development Environment Setup"
echo "========================================"

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed"
    exit 1
fi

echo "✅ Python 3 found: $(python3 --version)"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install development dependencies
echo "📚 Installing development dependencies..."
make install-dev

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "⚙️  Creating .env file from template..."
    cp env.sample .env
    echo "✏️  Please edit .env file with your configuration"
fi

# Install pre-commit hooks
echo "🪝 Setting up pre-commit hooks..."
pre-commit install

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p data logs

# Run initial tests to verify setup
echo "🧪 Running initial tests..."
make test-fast

echo ""
echo "🎉 Development environment setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your Signal configuration"
echo "2. Run 'make help' to see available commands"
echo "3. Run 'make run-emulation' to test the bot"
echo "4. Run 'make test' to run the full test suite"
echo ""
echo "Happy coding! 🚀"