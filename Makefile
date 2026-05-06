.PHONY: all test proto build build-greeter build-openai package package-greeter package-openai clean help

ADAPTER_NAME ?= greeter
PYTHON := bash -c 'export PATH="$$HOME/.local/bin:$$PATH" && cd /home/dave/Projects/astrocyte-python-adapter-sdk && uv run python'

all: test

proto:
	bash -c 'export PATH="$$HOME/.local/bin:$$PATH" && cd /home/dave/Projects/astrocyte-python-adapter-sdk && uv run python -m grpc_tools.protoc \
	  --proto_path=/home/dave/Projects/criteria/proto \
	  --python_out=src \
	  --grpc_python_out=src \
	  criteria/v1/adapter_plugin.proto criteria/v1/events.proto criteria/v1/criteria.proto criteria/v1/server.proto'

test:
	bash -c 'export PATH="$$HOME/.local/bin:$$PATH" && cd /home/dave/Projects/astrocyte-python-adapter-sdk && uv run pytest tests/ -v'

build:
	bash -c 'export PATH="$$HOME/.local/bin:$$PATH" && cd /home/dave/Projects/astrocyte-python-adapter-sdk && uv run python -m nuitka \
	  --onefile --standalone --python-flag=-OO \
	  --output-filename=criteria-adapter-$(ADAPTER_NAME) \
	  examples/$(ADAPTER_NAME)/main.py'

build-greeter:
	$(MAKE) ADAPTER_NAME=greeter build

build-openai:
	$(MAKE) ADAPTER_NAME=openai build

package:
	bash -c 'export PATH="$$HOME/.local/bin:$$PATH" && cd /home/dave/Projects/astrocyte-python-adapter-sdk && uv build'

package-greeter:
	$(MAKE) ADAPTER_NAME=greeter build
	@echo "Packaging criteria-adapter-greeter as OCI artifact..."
	@echo "Use oras push to distribute the binary."

package-openai:
	$(MAKE) ADAPTER_NAME=openai build
	@echo "Packaging criteria-adapter-openai as OCI artifact..."
	@echo "Use oras push to distribute the binary."

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

help:
	@echo "Available targets:"
	@echo "  make proto          - Regenerate Python protobuf bindings"
	@echo "  make test           - Run pytest suite"
	@echo "  make build          - Build adapter binary with Nuitka (default: greeter)"
	@echo "  make build-greeter  - Build greeter example"
	@echo "  make build-openai   - Build openai example"
	@echo "  make package        - Build Python wheel"
	@echo "  make clean          - Remove build artifacts"
