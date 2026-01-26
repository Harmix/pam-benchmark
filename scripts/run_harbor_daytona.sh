#!/bin/bash

# =============================================================================
# run_harbor_daytona.sh
#
# Script to build Docker image locally, push to Daytona as a snapshot,
# and run Harbor using that snapshot. This works around the limitation
# that Daytona cannot build from docker-compose.yaml directly.
#
# The workflow:
#   1. Build Docker image locally from Dockerfile (with project root as context)
#   2. Push local image to Daytona as a snapshot
#   3. Wait for snapshot to become active
#   4. Create a Daytona sandbox from the snapshot
#   5. Install Harbor inside the sandbox and run the evaluation
#
# Prerequisites:
#   - Docker installed and running
#   - Daytona CLI installed and authenticated (daytona auth login)
#   - Python 3.8+ with daytona-sdk installed (pip install daytona-sdk)
#   - DAYTONA_API_KEY environment variable set
#   - ANTHROPIC_API_KEY environment variable set (for Claude agents)
#
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# =============================================================================
# Configuration
# =============================================================================

# Default values
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TASK_DIR="${PROJECT_ROOT}/tasks/memtrack"
ENVIRONMENT_DIR="${TASK_DIR}/environment"
DOCKERFILE="${ENVIRONMENT_DIR}/Dockerfile"

# Snapshot and image configuration
IMAGE_NAME="pam-memtrack"
IMAGE_TAG="v1.0"
SNAPSHOT_NAME="pam-memtrack-snapshot"

# Daytona resource configuration (from task.toml)
DAYTONA_CPU=2
DAYTONA_MEMORY=4
DAYTONA_DISK=10

# Harbor configuration defaults
DATASET="memtrack@1.0"
REGISTRY_PATH="${PROJECT_ROOT}/datasets/memtrack/registry.json"
N_CONCURRENT=1
AGENT=""
MODEL=""
FORCE_BUILD=false
SKIP_SNAPSHOT_PUSH=false
EXTRA_HARBOR_ARGS=""
SANDBOX_TIMEOUT=1800  # 30 minutes default timeout for sandbox operations

# =============================================================================
# Functions
# =============================================================================

print_usage() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Build Docker image locally, push to Daytona as a snapshot, and run Harbor
inside the Daytona sandbox. This bypasses the docker-compose.yaml limitation.

The workflow:
  1. Build Docker image locally from Dockerfile
  2. Push local image to Daytona as a snapshot
  3. Wait for snapshot to become active
  4. Create a Daytona sandbox from the snapshot
  5. Run Harbor evaluation inside the sandbox

Required Arguments:
    -a, --agent AGENT             Agent to use (e.g., "claude-code", "terminus-2", "oracle")
    -m, --model MODEL             Model to use (e.g., "anthropic/claude-haiku-4-5")

Optional Arguments:
    -e, --experiment-name NAME    Name of the experiment (default: auto-generated)
    -c, --configs CONFIGS         Comma-separated list of config names (without .yaml extension)
    -d, --dataset NAME            Dataset name with version (default: ${DATASET})
    -r, --registry-path PATH      Path to the registry.json file (default: ${REGISTRY_PATH})
    -n, --n-concurrent NUM        Number of concurrent trials (default: ${N_CONCURRENT})
    --snapshot-name NAME          Name for the Daytona snapshot (default: ${SNAPSHOT_NAME})
    --image-name NAME             Name for the Docker image (default: ${IMAGE_NAME})
    --image-tag TAG               Tag for the Docker image (default: ${IMAGE_TAG})
    --cpu NUM                     CPU cores for Daytona sandbox (default: ${DAYTONA_CPU})
    --memory NUM                  Memory in GB for Daytona sandbox (default: ${DAYTONA_MEMORY})
    --disk NUM                    Disk in GB for Daytona sandbox (default: ${DAYTONA_DISK})
    --timeout NUM                 Timeout in seconds for sandbox operations (default: ${SANDBOX_TIMEOUT})
    --skip-snapshot-push          Skip building/pushing snapshot (use existing)
    -f, --force-build             Force rebuild of Docker image (--no-cache)
    --extra-args ARGS             Additional arguments to pass to harbor run
    -h, --help                    Show this help message

Environment Variables:
    DAYTONA_API_KEY               Required: Your Daytona API key
    ANTHROPIC_API_KEY             Required for Claude agents: Your Anthropic API key

Example:
    # Run with Claude Code agent
    $(basename "$0") \\
        -a claude-code \\
        -m anthropic/claude-haiku-4-5 \\
        -e my_experiment \\
        -c "config_1,config_2" \\
        -n 4

    # Run with oracle agent (for testing)
    $(basename "$0") \\
        -a oracle \\
        -e oracle_test \\
        --skip-snapshot-push

    # Use existing snapshot (skip build and push)
    $(basename "$0") \\
        -a claude-code \\
        -m anthropic/claude-haiku-4-5 \\
        --skip-snapshot-push \\
        --snapshot-name my-existing-snapshot

EOF
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "\n${CYAN}==>${NC} ${GREEN}$1${NC}"
}

# Check if required environment variables are set
check_env_vars() {
    local missing=false

    if [ -z "$DAYTONA_API_KEY" ]; then
        log_error "DAYTONA_API_KEY environment variable is not set"
        missing=true
    fi

    if [ "$AGENT" != "oracle" ] && [ -z "$ANTHROPIC_API_KEY" ]; then
        log_warning "ANTHROPIC_API_KEY not set - required for Claude-based agents"
    fi

    if [ "$missing" = true ]; then
        exit 1
    fi
}

# Check if required tools are installed
check_tools() {
    local missing=false

    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed or not in PATH"
        missing=true
    fi

    if ! command -v daytona &> /dev/null; then
        log_error "Daytona CLI is not installed or not in PATH"
        missing=true
    fi

    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is not installed or not in PATH"
        missing=true
    fi

    # Check if daytona-sdk is installed
    if ! python3 -c "import daytona" 2>/dev/null; then
        log_warning "daytona-sdk not installed. Installing..."
        pip3 install daytona-sdk || {
            log_error "Failed to install daytona-sdk"
            missing=true
        }
    fi

    if [ "$missing" = true ]; then
        exit 1
    fi
}

# Build Docker image locally
build_docker_image() {
    log_step "Building Docker image locally..."

    local full_image_name="${IMAGE_NAME}:${IMAGE_TAG}"

    log_info "Image name: ${full_image_name}"
    log_info "Dockerfile: ${DOCKERFILE}"
    log_info "Build context: ${PROJECT_ROOT}"

    # Build for linux/amd64 platform (required for Daytona)
    local build_cmd="docker build --platform=linux/amd64 -t ${full_image_name} -f ${DOCKERFILE} ${PROJECT_ROOT}"

    if [ "$FORCE_BUILD" = true ]; then
        build_cmd="${build_cmd} --no-cache"
    fi

    log_info "Running: ${build_cmd}"
    eval "$build_cmd"

    if [ $? -eq 0 ]; then
        log_success "Docker image built successfully: ${full_image_name}"
    else
        log_error "Failed to build Docker image"
        exit 1
    fi
}

# Push Docker image to Daytona as a snapshot
push_snapshot_to_daytona() {
    log_step "Pushing Docker image to Daytona as snapshot..."

    local full_image_name="${IMAGE_NAME}:${IMAGE_TAG}"

    log_info "Snapshot name: ${SNAPSHOT_NAME}"
    log_info "CPU: ${DAYTONA_CPU}, Memory: ${DAYTONA_MEMORY}GB, Disk: ${DAYTONA_DISK}GB"

    # Check if snapshot already exists and delete it if so
    log_info "Checking for existing snapshot..."
    if daytona snapshot list 2>/dev/null | grep -q "${SNAPSHOT_NAME}"; then
        log_warning "Snapshot '${SNAPSHOT_NAME}' already exists, deleting..."
        daytona snapshot delete "${SNAPSHOT_NAME}" --yes 2>/dev/null || true
        # Wait a moment for deletion to complete
        sleep 5
    fi

    # Push the local image to Daytona as a snapshot
    local push_cmd="daytona snapshot push ${full_image_name} \
        --name ${SNAPSHOT_NAME} \
        --cpu ${DAYTONA_CPU} \
        --memory ${DAYTONA_MEMORY} \
        --disk ${DAYTONA_DISK}"

    log_info "Running: ${push_cmd}"
    eval "$push_cmd"

    if [ $? -eq 0 ]; then
        log_success "Snapshot pushed successfully"
    else
        log_error "Failed to push snapshot to Daytona"
        exit 1
    fi

    # Wait for snapshot to become active
    wait_for_snapshot_active
}

# Wait for snapshot to become active
wait_for_snapshot_active() {
    log_info "Waiting for snapshot to become active..."

    local max_wait=600  # 10 minutes
    local wait_interval=10
    local elapsed=0

    while [ $elapsed -lt $max_wait ]; do
        # Get the full line for the snapshot and check if it contains ACTIVE
        local snapshot_line=$(daytona snapshot list 2>/dev/null | grep "${SNAPSHOT_NAME}" || echo "")
        
        if echo "$snapshot_line" | grep -qi "ACTIVE"; then
            log_success "Snapshot is now active"
            return 0
        elif echo "$snapshot_line" | grep -qiE "(ERROR|FAILED)"; then
            log_error "Snapshot creation failed"
            exit 1
        fi

        # Extract status for display (second column, but handle variable spacing)
        local status=$(echo "$snapshot_line" | awk '{print $2}')
        log_info "Snapshot status: ${status:-pending}. Waiting... (${elapsed}s/${max_wait}s)"
        sleep $wait_interval
        elapsed=$((elapsed + wait_interval))
    done

    log_error "Timeout waiting for snapshot to become active"
    exit 1
}

# Create Daytona sandbox and run Harbor inside it using Python SDK
run_harbor_in_daytona() {
    log_step "Creating Daytona sandbox and running Harbor inside..."

    # Read registry.json content to embed in sandbox
    local registry_content=""
    if [ -f "$REGISTRY_PATH" ]; then
        registry_content=$(cat "$REGISTRY_PATH" | python3 -c "import sys, json; print(json.dumps(sys.stdin.read()))")
    else
        log_error "Registry file not found: ${REGISTRY_PATH}"
        exit 1
    fi

    # Read task.toml content
    local task_toml_content=""
    local task_toml_path="${TASK_DIR}/task.toml"
    if [ -f "$task_toml_path" ]; then
        task_toml_content=$(cat "$task_toml_path" | python3 -c "import sys, json; print(json.dumps(sys.stdin.read()))")
    else
        log_warning "task.toml not found: ${task_toml_path}"
        task_toml_content='""'
    fi

    # Read instruction.md content
    local instruction_content=""
    local instruction_path="${TASK_DIR}/instruction.md"
    if [ -f "$instruction_path" ]; then
        instruction_content=$(cat "$instruction_path" | python3 -c "import sys, json; print(json.dumps(sys.stdin.read()))")
    else
        log_warning "instruction.md not found: ${instruction_path}"
        instruction_content='""'
    fi

    # Read solution/solve.sh content
    local solve_sh_content=""
    local solve_sh_path="${TASK_DIR}/solution/solve.sh"
    if [ -f "$solve_sh_path" ]; then
        solve_sh_content=$(cat "$solve_sh_path" | python3 -c "import sys, json; print(json.dumps(sys.stdin.read()))")
    else
        log_warning "solve.sh not found: ${solve_sh_path}"
        solve_sh_content='""'
    fi

    # Read tests/test.sh content
    local test_sh_content=""
    local test_sh_path="${TASK_DIR}/tests/test.sh"
    if [ -f "$test_sh_path" ]; then
        test_sh_content=$(cat "$test_sh_path" | python3 -c "import sys, json; print(json.dumps(sys.stdin.read()))")
    else
        log_warning "test.sh not found: ${test_sh_path}"
        test_sh_content='""'
    fi

    # Read tests/test_outputs.py content
    local test_outputs_py_content=""
    local test_outputs_py_path="${TASK_DIR}/tests/test_outputs.py"
    if [ -f "$test_outputs_py_path" ]; then
        test_outputs_py_content=$(cat "$test_outputs_py_path" | python3 -c "import sys, json; print(json.dumps(sys.stdin.read()))")
    else
        log_warning "test_outputs.py not found: ${test_outputs_py_path}"
        test_outputs_py_content='""'
    fi

    # Read solution/llm_judge_eval.py content
    local llm_judge_eval_content=""
    local llm_judge_eval_path="${TASK_DIR}/solution/llm_judge_eval.py"
    if [ -f "$llm_judge_eval_path" ]; then
        llm_judge_eval_content=$(cat "$llm_judge_eval_path" | python3 -c "import sys, json; print(json.dumps(sys.stdin.read()))")
    else
        log_warning "llm_judge_eval.py not found: ${llm_judge_eval_path}"
        llm_judge_eval_content='""'
    fi

    # Build the Harbor command that will run inside the sandbox
    # Note: We'll create the registry file inside the sandbox
    local harbor_cmd="harbor run -d ${DATASET} --registry-path /workspace/registry.json -a ${AGENT}"

    if [ -n "$MODEL" ]; then
        harbor_cmd="${harbor_cmd} -m ${MODEL}"
    fi

    harbor_cmd="${harbor_cmd} -n ${N_CONCURRENT}"

    if [ -n "$EXTRA_HARBOR_ARGS" ]; then
        harbor_cmd="${harbor_cmd} ${EXTRA_HARBOR_ARGS}"
    fi

    # Build environment variables dict for Python
    local env_vars="{"
    env_vars="${env_vars}'DAYTONA_API_KEY': '${DAYTONA_API_KEY}'"
    
    if [ -n "$ANTHROPIC_API_KEY" ]; then
        env_vars="${env_vars}, 'ANTHROPIC_API_KEY': '${ANTHROPIC_API_KEY}'"
    fi
    
    if [ -n "$EXPERIMENT_NAME" ]; then
        env_vars="${env_vars}, 'EXPERIMENT_NAME': '${EXPERIMENT_NAME}'"
    fi
    
    if [ -n "$TASK_CONFIGS" ]; then
        env_vars="${env_vars}, 'TASK_CONFIGS': '${TASK_CONFIGS}'"
    fi
    
    env_vars="${env_vars}}"

    log_info "Harbor command: ${harbor_cmd}"
    log_info "Sandbox timeout: ${SANDBOX_TIMEOUT}s"

    # Create a temporary Python script to run Harbor in the Daytona sandbox
    local python_script=$(mktemp)
    cat > "$python_script" << PYTHON_EOF
#!/usr/bin/env python3
"""
Script to create a Daytona sandbox from a snapshot and run Harbor inside it.
"""
import os
import sys
import json
import time
import base64

try:
    from daytona import Daytona, DaytonaConfig, CreateSandboxFromSnapshotParams, Resources
except ImportError:
    print("ERROR: daytona-sdk not installed. Run: pip install daytona-sdk")
    sys.exit(1)

# Configuration
SNAPSHOT_NAME = "${SNAPSHOT_NAME}"
SANDBOX_TIMEOUT = ${SANDBOX_TIMEOUT}
HARBOR_CMD = """${harbor_cmd}"""
ENV_VARS = ${env_vars}
REGISTRY_CONTENT = ${registry_content}
TASK_TOML_CONTENT = ${task_toml_content}
INSTRUCTION_CONTENT = ${instruction_content}
SOLVE_SH_CONTENT = ${solve_sh_content}
TEST_SH_CONTENT = ${test_sh_content}
TEST_OUTPUTS_PY_CONTENT = ${test_outputs_py_content}
LLM_JUDGE_EVAL_CONTENT = ${llm_judge_eval_content}

def main():
    print(f"Connecting to Daytona...")
    
    # Initialize Daytona client
    config = DaytonaConfig(api_key=os.environ.get("DAYTONA_API_KEY"))
    daytona = Daytona(config)
    
    sandbox = None
    try:
        print(f"Creating sandbox from snapshot: {SNAPSHOT_NAME}")
        
        # Create sandbox from snapshot
        params = CreateSandboxFromSnapshotParams(
            snapshot=SNAPSHOT_NAME,
            env_vars=ENV_VARS
        )
        
        sandbox = daytona.create(params, timeout=300)  # 5 min timeout for creation
        print(f"Sandbox created: {sandbox.id}")
        
        # Check if Harbor CLI is already installed, install if not
        print("Checking for Harbor CLI...")
        check_result = sandbox.process.exec("which harbor || command -v harbor", timeout=30)
        if check_result.exit_code == 0:
            print("Harbor CLI already installed")
        else:
            print("Installing Harbor CLI in sandbox...")
            install_result = sandbox.process.exec(
                "pip install harbor",
                timeout=300  # 5 min for installation
            )
            if install_result.exit_code != 0:
                print(f"ERROR: Harbor install failed: {install_result.result}")
                sys.exit(1)
            else:
                print("Harbor CLI installed successfully")
        
        # Helper function to write file content to sandbox
        def write_file_to_sandbox(path, content, executable=False):
            if not content:
                return
            # Use base64 encoding to safely transfer content
            encoded = base64.b64encode(content.encode()).decode()
            cmd = f"echo '{encoded}' | base64 -d > {path}"
            result = sandbox.process.exec(cmd, timeout=60)
            if result.exit_code != 0:
                print(f"WARNING: Failed to write {path}: {result.result}")
            elif executable:
                sandbox.process.exec(f"chmod +x {path}", timeout=10)
        
        # Create directory structure
        print("Creating task directory structure...")
        setup_cmds = [
            "mkdir -p /workspace/tasks/memtrack/environment",
            "mkdir -p /workspace/tasks/memtrack/solution",
            "mkdir -p /workspace/tasks/memtrack/tests",
            "mkdir -p /workspace/datasets/memtrack"
        ]
        for cmd in setup_cmds:
            result = sandbox.process.exec(cmd, timeout=30)
            if result.exit_code != 0:
                print(f"WARNING: Setup command failed: {cmd}")
        
        # Write registry.json
        print("Creating registry.json...")
        write_file_to_sandbox("/workspace/registry.json", REGISTRY_CONTENT)
        
        # Write task files
        print("Creating task files...")
        write_file_to_sandbox("/workspace/tasks/memtrack/task.toml", TASK_TOML_CONTENT)
        write_file_to_sandbox("/workspace/tasks/memtrack/instruction.md", INSTRUCTION_CONTENT)
        write_file_to_sandbox("/workspace/tasks/memtrack/solution/solve.sh", SOLVE_SH_CONTENT, executable=True)
        write_file_to_sandbox("/workspace/tasks/memtrack/solution/llm_judge_eval.py", LLM_JUDGE_EVAL_CONTENT)
        write_file_to_sandbox("/workspace/tasks/memtrack/tests/test.sh", TEST_SH_CONTENT, executable=True)
        write_file_to_sandbox("/workspace/tasks/memtrack/tests/test_outputs.py", TEST_OUTPUTS_PY_CONTENT)
        
        # Create symlinks to task data that was baked into the Docker image
        print("Creating symlinks to task data...")
        symlink_cmds = [
            # Link environment files from /task_data/
            "ln -sf /task_data/setup_and_run.sh /workspace/tasks/memtrack/environment/setup_and_run.sh",
            "ln -sf /task_data/INIT.md /workspace/tasks/memtrack/environment/INIT.md",
            "ln -sf /task_data/init.py /workspace/tasks/memtrack/environment/init.py",
            "ln -sf /task_data/INTRO_TEMPLATE.md /workspace/tasks/memtrack/environment/INTRO_TEMPLATE.md",
            "ln -sf /task_data/CLAUDE.md /workspace/tasks/memtrack/environment/CLAUDE.md",
            "ln -sf /task_data/parse_oracle_stub.py /workspace/tasks/memtrack/environment/parse_oracle_stub.py",
            # Link test configs and event histories
            "ln -sf /task_data/test_configs /workspace/datasets/memtrack/test_configs",
            "ln -sf /task_data/test_event_histories /workspace/datasets/memtrack/test_event_histories"
        ]
        for cmd in symlink_cmds:
            result = sandbox.process.exec(cmd, timeout=30)
            if result.exit_code != 0:
                print(f"WARNING: Symlink command failed: {cmd}")
        
        print("Task structure setup complete")
        
        # Run Harbor
        print(f"Running Harbor command: {HARBOR_CMD}")
        print("-" * 60)
        
        result = sandbox.process.exec(
            HARBOR_CMD,
            timeout=SANDBOX_TIMEOUT,
            cwd="/workspace"
        )
        
        print("-" * 60)
        print(f"Harbor output:")
        print(result.result)
        print(f"Exit code: {result.exit_code}")
        
        if result.exit_code != 0:
            print(f"ERROR: Harbor command failed with exit code {result.exit_code}")
            sys.exit(result.exit_code)
        
        print("Harbor run completed successfully!")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Clean up sandbox
        if sandbox:
            try:
                print(f"Cleaning up sandbox: {sandbox.id}")
                daytona.delete(sandbox)
                print("Sandbox deleted successfully")
            except Exception as e:
                print(f"WARNING: Failed to delete sandbox: {e}")

if __name__ == "__main__":
    main()
PYTHON_EOF

    log_info "Running Python script to create sandbox and execute Harbor..."
    python3 "$python_script"
    local exit_code=$?

    # Clean up temp file
    rm -f "$python_script"

    if [ $exit_code -eq 0 ]; then
        log_success "Harbor run in Daytona completed successfully"
    else
        log_error "Harbor run in Daytona failed with exit code: ${exit_code}"
        exit $exit_code
    fi
}

# =============================================================================
# Parse Arguments
# =============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        -a|--agent)
            AGENT="$2"
            shift 2
            ;;
        -m|--model)
            MODEL="$2"
            shift 2
            ;;
        -e|--experiment-name)
            EXPERIMENT_NAME="$2"
            shift 2
            ;;
        -c|--configs)
            TASK_CONFIGS="$2"
            shift 2
            ;;
        -d|--dataset)
            DATASET="$2"
            shift 2
            ;;
        -r|--registry-path)
            REGISTRY_PATH="$2"
            shift 2
            ;;
        -n|--n-concurrent)
            N_CONCURRENT="$2"
            shift 2
            ;;
        --snapshot-name)
            SNAPSHOT_NAME="$2"
            shift 2
            ;;
        --image-name)
            IMAGE_NAME="$2"
            shift 2
            ;;
        --image-tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        --cpu)
            DAYTONA_CPU="$2"
            shift 2
            ;;
        --memory)
            DAYTONA_MEMORY="$2"
            shift 2
            ;;
        --disk)
            DAYTONA_DISK="$2"
            shift 2
            ;;
        --timeout)
            SANDBOX_TIMEOUT="$2"
            shift 2
            ;;
        --skip-snapshot-push)
            SKIP_SNAPSHOT_PUSH=true
            shift
            ;;
        -f|--force-build)
            FORCE_BUILD=true
            shift
            ;;
        --extra-args)
            EXTRA_HARBOR_ARGS="$2"
            shift 2
            ;;
        -h|--help)
            print_usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            print_usage
            exit 1
            ;;
    esac
done

# =============================================================================
# Validate Arguments
# =============================================================================

if [ -z "$AGENT" ]; then
    log_error "Agent is required (-a/--agent)"
    print_usage
    exit 1
fi

# Model is required for non-oracle agents
if [ "$AGENT" != "oracle" ] && [ -z "$MODEL" ]; then
    log_error "Model is required (-m/--model) for agent '${AGENT}'"
    print_usage
    exit 1
fi

# Generate experiment name if not provided
if [ -z "$EXPERIMENT_NAME" ]; then
    EXPERIMENT_NAME="daytona_${AGENT}_$(date '+%Y%m%d_%H%M%S')"
fi

# =============================================================================
# Main Execution
# =============================================================================

log_info "=========================================="
log_info "Harbor on Daytona Runner"
log_info "=========================================="
log_info "Project Root: ${PROJECT_ROOT}"
log_info "Agent: ${AGENT}"
log_info "Model: ${MODEL:-'(not specified)'}"
log_info "Experiment Name: ${EXPERIMENT_NAME}"
log_info "Dataset: ${DATASET}"
log_info "Configs: ${TASK_CONFIGS:-'(all)'}"
log_info "Concurrent Trials: ${N_CONCURRENT}"
log_info "Snapshot Name: ${SNAPSHOT_NAME}"
log_info "Image: ${IMAGE_NAME}:${IMAGE_TAG}"
log_info "Resources: CPU=${DAYTONA_CPU}, Memory=${DAYTONA_MEMORY}GB, Disk=${DAYTONA_DISK}GB"
log_info "Sandbox Timeout: ${SANDBOX_TIMEOUT}s"
log_info "Skip Snapshot Push: ${SKIP_SNAPSHOT_PUSH}"
log_info "=========================================="

# Check prerequisites
log_step "Checking prerequisites..."
check_tools
check_env_vars

# Build and push snapshot (if not skipped)
if [ "$SKIP_SNAPSHOT_PUSH" = false ]; then
    build_docker_image
    push_snapshot_to_daytona
else
    log_info "Skipping snapshot build/push (using existing snapshot: ${SNAPSHOT_NAME})"
fi

# Run Harbor in Daytona sandbox
run_harbor_in_daytona

log_info "=========================================="
log_success "All done!"
log_info "=========================================="
