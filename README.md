# criteria-adapter-sdk

Python SDK for building Criteria adapter plugins. This SDK enables you to write out-of-process adapter plugins for the Criteria workflow engine using Python, with Nuitka compilation for native binary distribution via OCI.

## Features

- **Python-native** - Full type hints and IDE support
- **Simple API** - `serve()` function for quick adapters
- **Full control** - `serve_adapter()` for complex implementations
- **Nuitka compilation** - Single binary output for OCI distribution
- **Multi-arch** - Linux x86_64, Linux ARM64, macOS ARM64
- **gRPC transport** - Compatible with HashiCorp go-plugin

## Requirements

- Python 3.12+
- uv (for project management)
- Make (optional, for convenience targets)

## Quick Start with Make

The easiest way to build and install an adapter:

```bash
# Build and install the greeter adapter (default)
make build-greeter

# Or build the openai example
make build-openai

# Build for a custom adapter
make ADAPTER_NAME=my-adapter build
```

## Manual Installation

### 1. Install Dependencies

```bash
uv sync
```

### 2. Build an Adapter

```bash
# Build the SDK first
uv build

# Build an example adapter
uv run python -m nuitka --onefile --standalone \
  --output-filename=criteria-adapter-greeter \
  examples/greeter/main.py
```

### 3. Install to Criteria

```bash
mkdir -p ~/.criteria/plugins
cp criteria-adapter-greeter ~/.criteria/plugins/
chmod +x ~/.criteria/plugins/criteria-adapter-greeter
```

## Usage in Workflows

```hcl
step "analyze" {
  adapter = "greeter"

  agent {
    config {
      name = "world"
    }
  }

  input {
    prompt = "Say hello"
  }

  outcome "success" { transition_to = "done" }
  outcome "failure" { transition_to = "failed" }
}
```

Run the workflow:
```bash
criteria apply workflow.hcl
```

## Make Targets

| Target | Description |
|--------|-------------|
| `make` or `make test` | Run test suite |
| `make proto` | Regenerate Python protobuf bindings |
| `make build` | Build adapter binary (default: greeter) |
| `make build-greeter` | Build greeter example |
| `make build-openai` | Build openai example |
| `make package` | Build Python wheel |
| `make clean` | Remove build artifacts |
| `make help` | Show all available targets |

## Examples

### Greeter (Simple)

See `examples/greeter/` - The simplest possible adapter.

```bash
make build-greeter
```

### OpenAI (Agent)

See `examples/openai/` - Full agent adapter placeholder.

```bash
make build-openai
```

## API Reference

### `serve(config)`

Simplest way to create an adapter:

```python
from criteria_adapter_sdk import serve

async def main():
    await serve({
        "name": "my-adapter",
        "version": "1.0.0",
        "execute": lambda req, sender: sender.result("success", {}),
    })

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### `EventSender`

Stream events back to Criteria:

```python
class EventSender:
    async def log(stream: str, chunk: str | bytes) -> None: ...
    async def adapter_event(event: Any) -> None: ...
    async def permission_request(permission: str, details: dict[str, str]) -> str: ...
    async def result(outcome: str, outputs: dict[str, str]) -> None: ...
```

See `examples/openai/main.py` for a complete implementation.

## Project Structure

```
├── Makefile                      # Build and install targets
├── pyproject.toml                # uv project configuration
├── uv.lock                       # Cross-platform lockfile
├── src/
│   ├── criteria/                 # Generated protobuf bindings
│   │   └── v1/
│   └── criteria_adapter_sdk/     # SDK source code
│       ├── plugin/               # Core plugin SDK
│       └── proto/                # Proto bindings
├── examples/
│   ├── greeter/                  # Simple example
│   └── openai/                   # OpenAI agent adapter
└── tests/                        # Test suite
```

## Development

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Generate proto bindings
make proto

# Build wheel
uv build
```

## License

MIT
