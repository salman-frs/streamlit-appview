#!/bin/bash

# Unified Application Collector for Alibaba Cloud Instances
# Detects Docker/Podman containers and system services with port information
# Version: 1.0.8

set -euo pipefail

# Configuration defaults
DEBUG=${DEBUG:-true}
OUTPUT_FILE=${OUTPUT_FILE:-""}
TIMEOUT=${TIMEOUT:-360}
INCLUDE_PORTS=${INCLUDE_PORTS:-""}
EXCLUDE_PORTS=${EXCLUDE_PORTS:-""}
CONTAINER_RUNTIME_PRIORITY=${CONTAINER_RUNTIME_PRIORITY:-"docker,podman"}
DETECT_SYSTEM_SERVICES=${DETECT_SYSTEM_SERVICES:-true}
JSON_PRETTY=${JSON_PRETTY:-true}

# OSS Configuration
OSS_UPLOAD_ENABLED=${OSS_UPLOAD_ENABLED:-false}
OSS_ENDPOINT=${OSS_ENDPOINT:-""}
OSS_ACCESS_KEY_ID=${OSS_ACCESS_KEY_ID:-""}
OSS_ACCESS_KEY_SECRET=${OSS_ACCESS_KEY_SECRET:-""}
OSS_BUCKET=${OSS_BUCKET:-""}
OSS_PREFIX=${OSS_PREFIX:-""}
OSS_STS_TOKEN=${OSS_STS_TOKEN:-""}

# Load configuration if exists
if [[ -f "$(dirname "$0")/../config/collection.conf" ]]; then
    source "$(dirname "$0")/../config/collection.conf"
fi

# Load OSS configuration if exists
if [[ -f "$(dirname "$0")/../config/oss.conf" ]]; then
    source "$(dirname "$0")/../config/oss.conf"
fi

# Debug function
debug() {
    if [[ "$DEBUG" == "true" ]]; then
        echo "[DEBUG] $*" >&2
    fi
}

# Detect OS and install dependencies
detect_os_and_install_deps() {
    debug "Detecting operating system..."
    
    local os_type="unknown"
    local package_manager=""
    
    # Detect OS
    if [[ -f /etc/os-release ]]; then
        source /etc/os-release
        case "$ID" in
            ubuntu|debian)
                os_type="debian"
                package_manager="apt-get"
                ;;
            centos|rhel|fedora|rocky|almalinux)
                os_type="redhat"
                package_manager="yum"
                if command_exists dnf; then
                    package_manager="dnf"
                fi
                ;;
            alpine)
                os_type="alpine"
                package_manager="apk"
                ;;
            arch)
                os_type="arch"
                package_manager="pacman"
                ;;
        esac
    elif [[ "$(uname)" == "Darwin" ]]; then
        os_type="macos"
        package_manager="brew"
    fi
    
    debug "Detected OS: $os_type, Package manager: $package_manager"
    
    # Install missing dependencies
    local deps_to_install=()
    
    # Check for required tools
    if ! command_exists curl; then
        deps_to_install+=("curl")
    fi
    
    if ! command_exists jq; then
        deps_to_install+=("jq")
    fi
    
    if ! command_exists ss && ! command_exists netstat; then
        case "$os_type" in
            debian)
                deps_to_install+=("iproute2" "net-tools")
                ;;
            redhat)
                deps_to_install+=("iproute" "net-tools")
                ;;
            alpine)
                deps_to_install+=("iproute2" "net-tools")
                ;;
            arch)
                deps_to_install+=("iproute2" "net-tools")
                ;;
            macos)
                deps_to_install+=("iproute2mac")
                ;;
        esac
    fi
    
    # Install dependencies if any are missing
    if [[ ${#deps_to_install[@]} -gt 0 ]]; then
        debug "Installing missing dependencies: ${deps_to_install[*]}"
        
        case "$package_manager" in
            apt-get)
                sudo apt-get update -qq
                sudo apt-get install -y "${deps_to_install[@]}"
                ;;
            yum|dnf)
                sudo "$package_manager" install -y "${deps_to_install[@]}"
                ;;
            apk)
                sudo apk add "${deps_to_install[@]}"
                ;;
            pacman)
                sudo pacman -S --noconfirm "${deps_to_install[@]}"
                ;;
            brew)
                brew install "${deps_to_install[@]}"
                ;;
            *)
                debug "Warning: Unknown package manager. Please install manually: ${deps_to_install[*]}"
                ;;
        esac
    else
        debug "All required dependencies are already installed"
    fi
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Get instance metadata
get_instance_metadata() {
    local instance_id="unknown"
    local instance_name="unknown"
    
    # Try Alibaba Cloud metadata
    if command_exists curl; then
        # Get instance ID
        instance_id=$(curl -s --connect-timeout 5 "http://100.100.100.200/latest/meta-data/instance-id" 2>/dev/null || echo "")
        
        # Get instance name from tags or hostname
        instance_name=$(curl -s --connect-timeout 5 "http://100.100.100.200/latest/meta-data/hostname" 2>/dev/null || echo "")
        
        # Try to get instance name from instance attributes if available
        if [[ -z "$instance_name" || "$instance_name" == "unknown" ]]; then
            instance_name=$(curl -s --connect-timeout 5 "http://100.100.100.200/latest/meta-data/instance/instance-name" 2>/dev/null || echo "")
        fi
    fi
    
    # Fallback to hostname for both if metadata is not available
    if [[ -z "$instance_id" || "$instance_id" == "unknown" ]]; then
        instance_id=$(hostname 2>/dev/null || echo "localhost")
    fi
    
    if [[ -z "$instance_name" || "$instance_name" == "unknown" ]]; then
        instance_name=$(hostname 2>/dev/null || echo "localhost")
    fi
    
    echo "${instance_id}|${instance_name}"
}

# Get listening ports
get_listening_ports() {
    local -a ports=()
    
    if command_exists ss; then
        while IFS= read -r line; do
            if [[ -n "$line" ]]; then
                ports+=("$line")
            fi
        done < <(ss -tlnp 2>/dev/null | grep LISTEN || true)
    elif command_exists netstat; then
        while IFS= read -r line; do
            if [[ -n "$line" ]]; then
                ports+=("$line")
            fi
        done < <(netstat -tlnp 2>/dev/null | grep LISTEN || true)
    fi
    
    printf '%s\n' "${ports[@]}"
}

# Extract port from netstat/ss output
extract_port_info() {
    local line="$1"
    local port=""
    local pid=""
    
    debug "Processing line: $line"
    
    if echo "$line" | grep -q ":" && echo "$line" | grep -q "LISTEN"; then
        # Extract port number
        port=$(echo "$line" | awk '{print $4}' | sed 's/.*://' | sed 's/\s.*//')
        
        # Extract PID (take only the first PID if multiple exist)
        if echo "$line" | grep -q "pid="; then
            pid=$(echo "$line" | grep -o 'pid=[0-9]*' | head -1 | cut -d'=' -f2)
        elif echo "$line" | grep -qE '[0-9]+/'; then
            pid=$(echo "$line" | grep -oE '[0-9]+/' | head -1 | cut -d'/' -f1)
        fi
        
        debug "Extracted port: $port, pid: $pid"
    fi
    
    if [[ -n "$port" ]]; then
        echo "${port}:${pid:-unknown}"
    fi
}

# Parse container ports from docker/podman ps output
parse_container_ports() {
    local ports_string="$1"
    local -a container_ports=()
    
    if [[ -n "$ports_string" && "$ports_string" != "" ]]; then
        # Extract external port numbers from format like "0.0.0.0:8038->8038/tcp, :::8038->8038/tcp"
        # Also handle internal ports like "3306/tcp"
        while IFS= read -r port; do
            if [[ -n "$port" ]]; then
                container_ports+=("$port")
            fi
        done < <(echo "$ports_string" | grep -oE '([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:|\[::\]:)?[0-9]+' | grep -oE '[0-9]+$' | sort -u)
        
        # Also extract internal ports that are not mapped externally
        while IFS= read -r port; do
            if [[ -n "$port" ]]; then
                container_ports+=("$port")
            fi
        done < <(echo "$ports_string" | grep -oE '[0-9]+/(tcp|udp)' | cut -d'/' -f1 | sort -u)
    fi
    
    # Remove duplicates and sort
    if [[ ${#container_ports[@]} -gt 0 ]]; then
        printf '%s\n' "${container_ports[@]}" | sort -u
    fi
}

# Detect Docker containers
detect_docker_containers() {
    local -a containers=()
    
    if ! command_exists docker; then
        printf '%s\n' "${containers[@]}"
        return
    fi
    
    debug "Detecting Docker containers..."
    
    while IFS='|' read -r container_id name image status ports; do
        debug "Docker line: $container_id|$name|$image|$status|$ports"
        if [[ -n "$container_id" && "$container_id" != "CONTAINER" ]]; then
            # Skip containers that are not running (filter out Exited, Created, etc.)
            if [[ "$status" =~ ^Exited || "$status" =~ ^Created || "$status" =~ ^Dead ]]; then
                debug "Skipping inactive container: $name (status: $status)"
                continue
            fi
            
            # Get container PID
            local container_pid
            container_pid=$(docker inspect "$container_id" --format '{{.State.Pid}}' 2>/dev/null || echo "")
            
            # Parse container ports from docker ps output
            local -a container_ports=()
            while IFS= read -r port; do
                if [[ -n "$port" ]]; then
                    container_ports+=("$port")
                fi
            done < <(parse_container_ports "$ports")
            
            # Format ports as JSON array
            local ports_json="[]"
            if [[ ${#container_ports[@]} -gt 0 ]]; then
                local ports_str
                ports_str=$(printf '"%s",' "${container_ports[@]}")
                ports_str=${ports_str%,}
                ports_json="[$ports_str]"
            fi
            
            # Escape JSON values
            local escaped_name escaped_image escaped_status escaped_container_id
            escaped_name=$(printf '%s' "$name" | sed 's/"/\\"/g' | sed 's/\\/\\\\/g')
            escaped_image=$(printf '%s' "$image" | sed 's/"/\\"/g' | sed 's/\\/\\\\/g')
            escaped_status=$(printf '%s' "$status" | sed 's/"/\\"/g' | sed 's/\\/\\\\/g')
            escaped_container_id=$(printf '%s' "$container_id" | sed 's/"/\\"/g' | sed 's/\\/\\\\/g')
            
            # Only add container if we have valid data
            if [[ -n "$escaped_name" && -n "$escaped_image" && -n "$escaped_status" && -n "$escaped_container_id" ]]; then
                local container_json
                local pid_array="[\"${container_pid:-unknown}\"]"
                container_json='{"name":"'$escaped_name'","type":"docker","image":"'$escaped_image'","status":"'$escaped_status'","ports":'$ports_json',"pids":'$pid_array',"container_id":"'$escaped_container_id'"}'
                containers+=("$container_json")
                debug "Added running container: $name"
            fi
        fi
    done < <(docker ps -a --format "{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}" 2>/dev/null || true)
    
    printf '%s\n' "${containers[@]}"
}

# Detect Podman containers
detect_podman_containers() {
    local -a containers=()
    
    if ! command_exists podman; then
        printf '%s\n' "${containers[@]}"
        return
    fi
    
    debug "Detecting Podman containers..."
    
    while IFS='|' read -r container_id name image status ports; do
        if [[ -n "$container_id" && "$container_id" != "CONTAINER" ]]; then
            # Skip containers that are not running (filter out Exited, Created, etc.)
            if [[ "$status" =~ ^Exited || "$status" =~ ^Created || "$status" =~ ^Dead ]]; then
                debug "Skipping inactive podman container: $name (status: $status)"
                continue
            fi
            
            # Get container PID
            local container_pid
            container_pid=$(podman inspect "$container_id" --format '{{.State.Pid}}' 2>/dev/null || echo "")
            
            # Parse container ports from podman ps output
            local -a container_ports=()
            while IFS= read -r port; do
                if [[ -n "$port" ]]; then
                    container_ports+=("$port")
                fi
            done < <(parse_container_ports "$ports")
            
            # Format ports as JSON array
            local ports_json="[]"
            if [[ ${#container_ports[@]} -gt 0 ]]; then
                local ports_str
                ports_str=$(printf '"%s",' "${container_ports[@]}")
                ports_str=${ports_str%,}
                ports_json="[$ports_str]"
            fi
            
            # Escape JSON values
            local escaped_name escaped_image escaped_status escaped_container_id
            escaped_name=$(printf '%s' "$name" | sed 's/"/\\"/g' | sed 's/\\/\\\\/g')
            escaped_image=$(printf '%s' "$image" | sed 's/"/\\"/g' | sed 's/\\/\\\\/g')
            escaped_status=$(printf '%s' "$status" | sed 's/"/\\"/g' | sed 's/\\/\\\\/g')
            escaped_container_id=$(printf '%s' "$container_id" | sed 's/"/\\"/g' | sed 's/\\/\\\\/g')
            
            # Only add container if we have valid data
            if [[ -n "$escaped_name" && -n "$escaped_image" && -n "$escaped_status" && -n "$escaped_container_id" ]]; then
                local container_json
                local pid_array="[\"${container_pid:-unknown}\"]"
                container_json='{"name":"'$escaped_name'","type":"podman","image":"'$escaped_image'","status":"'$escaped_status'","ports":'$ports_json',"pids":'$pid_array',"container_id":"'$escaped_container_id'"}'
                containers+=("$container_json")
            fi
        fi
    done < <(podman ps -a --format "{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}" 2>/dev/null || true)
    
    printf '%s\n' "${containers[@]}"
}

# Detect system services
detect_system_services() {
    local -a services=()
    
    if [[ "$DETECT_SYSTEM_SERVICES" != "true" ]]; then
        printf '%s\n' "${services[@]}"
        return
    fi
    
    debug "Detecting system services..."
    
    # Get all container PIDs to exclude them
    local -a container_pids=()
    
    # Docker PIDs
    if command_exists docker; then
        while IFS= read -r pid; do
            if [[ -n "$pid" && "$pid" != "0" ]]; then
                container_pids+=("$pid")
            fi
        done < <(docker ps -q 2>/dev/null | xargs -I {} docker inspect {} --format '{{.State.Pid}}' 2>/dev/null || true)
    fi
    
    # Podman PIDs
    if command_exists podman; then
        while IFS= read -r pid; do
            if [[ -n "$pid" && "$pid" != "0" ]]; then
                container_pids+=("$pid")
            fi
        done < <(podman ps -q 2>/dev/null | xargs -I {} podman inspect {} --format '{{.State.Pid}}' 2>/dev/null || true)
    fi
    
    # Get listening ports and find non-container processes
    while IFS= read -r port_line; do
        if [[ -n "$port_line" ]]; then
            local port_info
            port_info=$(extract_port_info "$port_line")
            if [[ -n "$port_info" ]]; then
                local port pid
                port=$(echo "$port_info" | cut -d':' -f1)
                pid=$(echo "$port_info" | cut -d':' -f2)
                
                # Skip if PID is unknown or if it's a container PID
                if [[ "$pid" == "unknown" ]]; then
                    continue
                fi
                
                local is_container_pid=false
                for container_pid in "${container_pids[@]}"; do
                    if [[ "$pid" == "$container_pid" ]]; then
                        is_container_pid=true
                        break
                    fi
                done
                
                if [[ "$is_container_pid" == "false" ]]; then
                    # Get process name
                    local process_name
                    process_name=$(ps -p "$pid" -o comm= 2>/dev/null || echo "unknown")
                    debug "Found non-container service: port=$port, pid=$pid, process=$process_name"
                    
                    # Determine service type
                    local service_type="process"
                    if command_exists systemctl && systemctl --quiet is-active "$process_name" 2>/dev/null; then
                        service_type="systemd"
                    fi
                    
                    # Escape JSON values
                    local escaped_process_name
                    escaped_process_name=$(printf '%s' "$process_name" | sed 's/"/\\"/g' | sed 's/\\/\\\\/g')
                    
                    # Only add service if we have valid data
                    if [[ -n "$escaped_process_name" && -n "$pid" && -n "$port" ]]; then
                        local service_json
                        local pid_array="[\"$pid\"]"
                        service_json='{"name":"'$escaped_process_name'","type":"'$service_type'","image":null,"status":"running","ports":["'$port'"],"pids":'$pid_array',"process_name":"'$escaped_process_name'"}'
                        services+=("$service_json")
                    fi
                fi
            fi
        fi
    done < <(get_listening_ports)
    
    printf '%s\n' "${services[@]}"
}

# Function to deduplicate applications by merging same name+type combinations
deduplicate_applications() {
    local -a applications=("$@")
    local -A app_map
    local -a result=()
    
    # Process each application
    for app_json in "${applications[@]}"; do
        if [[ -n "$app_json" ]]; then
            # Extract name and type using jq
            local name type
            name=$(echo "$app_json" | jq -r '.name // "unknown"' 2>/dev/null)
            type=$(echo "$app_json" | jq -r '.type // "unknown"' 2>/dev/null)
            
            if [[ "$name" != "null" && "$type" != "null" && "$name" != "unknown" && "$type" != "unknown" ]]; then
                local key="${name}:${type}"
                
                if [[ -n "${app_map[$key]:-}" ]]; then
                    # Merge with existing application
                    local existing_json="${app_map[$key]}"
                    local merged_json
                    merged_json=$(merge_applications "$existing_json" "$app_json")
                    app_map["$key"]="$merged_json"
                    debug "Merged duplicate application: $name ($type)"
                else
                    # First occurrence of this application
                    app_map["$key"]="$app_json"
                fi
            fi
        fi
    done
    
    # Output deduplicated applications as JSON array
    local apps_array="["
    local first=true
    for key in "${!app_map[@]}"; do
        if [[ "$first" == true ]]; then
            first=false
        else
            apps_array="$apps_array,"
        fi
        apps_array="$apps_array${app_map[$key]}"
    done
    apps_array="$apps_array]"
    echo "$apps_array"
}

# Function to merge two application JSON objects
merge_applications() {
    local app1="$1"
    local app2="$2"
    
    # Extract data from both applications
    local name1 type1 image1 status1 container_id1 process_name1
    local name2 type2 image2 status2 container_id2 process_name2
    
    name1=$(echo "$app1" | jq -r '.name // ""' 2>/dev/null)
    type1=$(echo "$app1" | jq -r '.type // ""' 2>/dev/null)
    image1=$(echo "$app1" | jq -r '.image // null' 2>/dev/null)
    status1=$(echo "$app1" | jq -r '.status // ""' 2>/dev/null)
    container_id1=$(echo "$app1" | jq -r '.container_id // null' 2>/dev/null)
    process_name1=$(echo "$app1" | jq -r '.process_name // null' 2>/dev/null)
    
    name2=$(echo "$app2" | jq -r '.name // ""' 2>/dev/null)
    type2=$(echo "$app2" | jq -r '.type // ""' 2>/dev/null)
    image2=$(echo "$app2" | jq -r '.image // null' 2>/dev/null)
    status2=$(echo "$app2" | jq -r '.status // ""' 2>/dev/null)
    container_id2=$(echo "$app2" | jq -r '.container_id // null' 2>/dev/null)
    process_name2=$(echo "$app2" | jq -r '.process_name // null' 2>/dev/null)
    
    # Merge ports arrays
    local ports1_json ports2_json merged_ports_json
    ports1_json=$(echo "$app1" | jq -r '.ports // []' 2>/dev/null)
    ports2_json=$(echo "$app2" | jq -r '.ports // []' 2>/dev/null)
    merged_ports_json=$(echo "[$ports1_json, $ports2_json]" | jq 'flatten | unique | sort' 2>/dev/null)
    
    # Merge PIDs arrays
    local pids1_json pids2_json merged_pids_json
    pids1_json=$(echo "$app1" | jq -r '.pids // []' 2>/dev/null)
    pids2_json=$(echo "$app2" | jq -r '.pids // []' 2>/dev/null)
    merged_pids_json=$(echo "[$pids1_json, $pids2_json]" | jq 'flatten | unique | sort' 2>/dev/null)
    
    # Use values from first application as base, prefer non-null values
    local final_image final_container_id final_process_name
    final_image="$image1"
    [[ "$final_image" == "null" && "$image2" != "null" ]] && final_image="$image2"
    
    final_container_id="$container_id1"
    [[ "$final_container_id" == "null" && "$container_id2" != "null" ]] && final_container_id="$container_id2"
    
    final_process_name="$process_name1"
    [[ "$final_process_name" == "null" && "$process_name2" != "null" ]] && final_process_name="$process_name2"
    
    # Ensure JSON values are properly formatted for jq
    [[ "$final_image" == "null" ]] && final_image="null" || final_image="\"$final_image\""
    [[ "$final_container_id" == "null" ]] && final_container_id="null" || final_container_id="\"$final_container_id\""
    [[ "$final_process_name" == "null" ]] && final_process_name="null" || final_process_name="\"$final_process_name\""
    
    # Validate merged JSON arrays
    [[ -z "$merged_ports_json" || "$merged_ports_json" == "null" ]] && merged_ports_json="[]"
    [[ -z "$merged_pids_json" || "$merged_pids_json" == "null" ]] && merged_pids_json="[]"
    
    # Create merged JSON using jq for proper formatting
    local merged_json
    if [[ "$final_container_id" != "null" ]]; then
        # Docker/Podman container
        merged_json=$(jq -n \
            --arg name "$name1" \
            --arg type "$type1" \
            --argjson image "$final_image" \
            --arg status "$status1" \
            --argjson ports "$merged_ports_json" \
            --argjson pids "$merged_pids_json" \
            --argjson container_id "$final_container_id" \
            '{name: $name, type: $type, image: $image, status: $status, ports: $ports, pids: $pids, container_id: $container_id}')
    else
        # System service/process
        merged_json=$(jq -n \
            --arg name "$name1" \
            --arg type "$type1" \
            --argjson image "$final_image" \
            --arg status "$status1" \
            --argjson ports "$merged_ports_json" \
            --argjson pids "$merged_pids_json" \
            --argjson process_name "$final_process_name" \
            '{name: $name, type: $type, image: $image, status: $status, ports: $ports, pids: $pids, process_name: $process_name}')
    fi
    
    echo "$merged_json"
}

# Main function
main() {
    debug "Starting unified application collector..."
    
    # Detect OS and install dependencies if needed
    detect_os_and_install_deps
    
    # Get instance information
    local instance_metadata instance_id instance_name
    instance_metadata=$(get_instance_metadata)
    instance_id=$(echo "$instance_metadata" | cut -d'|' -f1)
    instance_name=$(echo "$instance_metadata" | cut -d'|' -f2)
    local timestamp
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    
    debug "Instance ID: $instance_id"
    debug "Instance Name: $instance_name"
    debug "Timestamp: $timestamp"
    
    # Collect all applications
    local -a all_applications=()
    
    # Detect containers based on priority
    IFS=',' read -ra runtimes <<< "$CONTAINER_RUNTIME_PRIORITY"
    for runtime in "${runtimes[@]}"; do
        case "$runtime" in
            "docker")
                while IFS= read -r container; do
                    if [[ -n "$container" ]]; then
                        all_applications+=("$container")
                    fi
                done < <(detect_docker_containers)
                ;;
            "podman")
                while IFS= read -r container; do
                    if [[ -n "$container" ]]; then
                        all_applications+=("$container")
                    fi
                done < <(detect_podman_containers)
                ;;
        esac
    done
    
    # Detect system services
    while IFS= read -r service; do
        if [[ -n "$service" ]]; then
            all_applications+=("$service")
        fi
    done < <(detect_system_services)
    
    # Format applications as JSON array
    local applications_json="[]"
    debug "Total applications collected: ${#all_applications[@]}"
    if [[ ${#all_applications[@]} -gt 0 ]]; then
        # Filter out empty or invalid JSON objects
        local -a valid_applications=()
        for app in "${all_applications[@]}"; do
            debug "Validating application JSON: $app"
            if [[ -n "$app" ]] && echo "$app" | jq . >/dev/null 2>&1; then
                valid_applications+=("$app")
                debug "Application JSON is valid"
            else
                debug "Application JSON is invalid or empty"
            fi
        done
        
        debug "Valid applications count: ${#valid_applications[@]}"
        if [[ ${#valid_applications[@]} -gt 0 ]]; then
            # Deduplicate applications by merging same name+type combinations
            applications_json=$(deduplicate_applications "${valid_applications[@]}")
            local app_count
            app_count=$(echo "$applications_json" | jq '. | length' 2>/dev/null || echo "0")
            debug "Deduplicated applications count: $app_count"
            debug "Final applications JSON: $applications_json"
        fi
    fi
    
    # Ensure applications_json is always valid JSON
    if [[ -z "$applications_json" ]] || ! echo "$applications_json" | jq . >/dev/null 2>&1; then
        applications_json="[]"
    fi
    
    # Escape instance data for JSON
    local escaped_instance_id escaped_instance_name
    escaped_instance_id=$(printf '%s' "$instance_id" | sed 's/"/\\"/g' | sed 's/\\/\\\\/g')
    escaped_instance_name=$(printf '%s' "$instance_name" | sed 's/"/\\"/g' | sed 's/\\/\\\\/g')
    
    # Create final JSON output
    local output_json
    output_json=$(cat <<EOF
{
  "instance_id": "$escaped_instance_id",
  "instance_name": "$escaped_instance_name",
  "collection_timestamp": "$timestamp",
  "script_version": "1.0.9",
  "applications": $applications_json,
  "total_applications": $(echo "$applications_json" | jq 'length' 2>/dev/null || echo 0)
}
EOF
    )
    
    # Pretty print if enabled
    if [[ "$JSON_PRETTY" == "true" ]] && command_exists jq; then
        output_json=$(echo "$output_json" | jq .)
    fi
    
    # Output to file or stdout
    if [[ -n "$OUTPUT_FILE" ]]; then
        echo "$output_json" > "$OUTPUT_FILE"
        debug "Output written to: $OUTPUT_FILE"
    else
        echo "$output_json"
    fi
    
    # Upload to OSS if enabled
    if [[ "$OSS_UPLOAD_ENABLED" == "true" ]]; then
        upload_to_oss "$output_json" "$instance_id" "$instance_name" "$timestamp"
    fi
    
    debug "Collection completed. Found ${#all_applications[@]} applications."
}

# Upload JSON data to Alibaba Cloud OSS
upload_to_oss() {
    local json_data="$1"
    local instance_id="$2"
    local instance_name="$3"
    local timestamp="$4"
    
    debug "Starting OSS upload..."
    
    # Validate required OSS configuration
    if [[ -z "$OSS_ENDPOINT" ]] || [[ -z "$OSS_ACCESS_KEY_ID" ]] || [[ -z "$OSS_ACCESS_KEY_SECRET" ]] || [[ -z "$OSS_BUCKET" ]]; then
        echo "[ERROR] OSS upload enabled but missing required configuration:" >&2
        echo "  OSS_ENDPOINT: ${OSS_ENDPOINT:-'(not set)'}" >&2
        echo "  OSS_ACCESS_KEY_ID: ${OSS_ACCESS_KEY_ID:-'(not set)'}" >&2
        echo "  OSS_ACCESS_KEY_SECRET: ${OSS_ACCESS_KEY_SECRET:-'(not set)'}" >&2
        echo "  OSS_BUCKET: ${OSS_BUCKET:-'(not set)'}" >&2
        return 1
    fi
    
    # Check if ossutil is available, install if needed
    if ! command_exists ossutil; then
        echo "[INFO] ossutil not found. Installing ossutil automatically..." >&2
        
        # Install ossutil
        if curl -s https://gosspublic.alicdn.com/ossutil/install.sh | sudo bash; then
            echo "[INFO] ossutil installed successfully" >&2
            
            # Verify installation
            if ! command_exists ossutil; then
                echo "[ERROR] ossutil installation failed - command not found after installation" >&2
                return 1
            fi
        else
            echo "[ERROR] Failed to install ossutil" >&2
            echo "Please install manually: sudo -v ; curl https://gosspublic.alicdn.com/ossutil/install.sh | sudo bash" >&2
            return 1
        fi
    fi
    
    # Create unique filename with instance ID and name
    local safe_instance_name
    safe_instance_name=$(echo "$instance_name" | sed 's/[^a-zA-Z0-9._-]/_/g')
    local date_formatted
    date_formatted=$(echo "$timestamp" | sed 's/[T:]/_/g' | sed 's/Z$//' | cut -d'_' -f1-2 | tr '_' '_')
    local filename="${instance_id}_${safe_instance_name}_${date_formatted}.json"
    local oss_path="${OSS_PREFIX}${filename}"
    
    # Create temporary file
    local temp_file
    temp_file=$(mktemp)
    echo "$json_data" > "$temp_file"
    
    debug "Uploading to OSS: oss://$OSS_BUCKET/$oss_path"
    
    # Build ossutil command
    local ossutil_cmd=("ossutil" "cp" "$temp_file" "oss://$OSS_BUCKET/$oss_path")
    ossutil_cmd+=("--endpoint" "$OSS_ENDPOINT")
    ossutil_cmd+=("--access-key-id" "$OSS_ACCESS_KEY_ID")
    ossutil_cmd+=("--access-key-secret" "$OSS_ACCESS_KEY_SECRET")
    
    # Add STS token if provided
    if [[ -n "$OSS_STS_TOKEN" ]]; then
        ossutil_cmd+=("--sts-token" "$OSS_STS_TOKEN")
    fi
    
    # Execute upload
    if "${ossutil_cmd[@]}" 2>/dev/null; then
        echo "[INFO] Successfully uploaded to OSS: oss://$OSS_BUCKET/$oss_path"
        debug "OSS upload completed successfully"
    else
        echo "[ERROR] Failed to upload to OSS" >&2
        rm -f "$temp_file"
        return 1
    fi
    
    # Clean up temporary file
    rm -f "$temp_file"
    debug "Temporary file cleaned up"
}

# Run main function
main "$@"