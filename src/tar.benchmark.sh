#!/bin/bash

# Function to show numbered directory listing and get user selection
select_directory() {
    local prefix="$1"
    local current_path="${2:-.}"  # Default to current directory if not specified
    local start_dir=$(pwd)
    local full_path="$start_dir/${current_path#./}"  # Remove leading ./ if present
    local dirs=()
    local i=1

    # Show current path context
    echo "Location: $full_path"
    echo "---"

    # Get all directories in current path, optionally filtered by prefix
    while IFS= read -r dir; do
        dirs+=("$dir")
        echo "$i) $dir"
        ((i++))
    done < <(find "$current_path" -maxdepth 1 -type d -not -name "." | sed "s|^$current_path/||" | sort | \
             if [ -n "$prefix" ]; then grep "^$prefix" || true; else cat; fi)

    # If no directories found
    test ${#dirs[@]} || {
        echo "No directories found${prefix:+ starting with '$prefix'}"
        exit 1
    }

    # Prompt user for selection
    while true; do
        read -p "Select number (1-${#dirs[@]}), prefix filter, number/ to dive in, or .. to go up: " selection
        case "$selection" in
            "..")
                if [ "$current_path" != "." ]; then
                    select_directory "" "${current_path%/*}"
                    return
                fi
                echo "Already at top level"
                ;;
            */)  # Ends with slash - dive into directory
                num="${selection%/}"
                if [[ "$num" =~ ^[0-9]+$ ]] && [ "$num" -ge 1 ] && [ "$num" -le "${#dirs[@]}" ]; then
                    select_directory "" "$current_path/${dirs[$num-1]}"
                    return
                fi
                echo "Invalid directory number for diving in"
                ;;
            [0-9]*)  # Starts with number - final selection
                if [ "$selection" -ge 1 ] && [ "$selection" -le "${#dirs[@]}" ]; then
                    benchmark_folder="$current_path/${dirs[$selection-1]}"
                    break
                fi
                echo "Invalid selection. Please choose a number between 1 and ${#dirs[@]}"
                ;;
            *)  # Use as prefix filter at current level
                select_directory "$selection" "$current_path"
                return
                ;;
        esac
    done
}

# Main script
benchmark_folder="$1"
test "$benchmark_folder" || select_directory

# Validate benchmark_folder is not empty
test "$benchmark_folder" || {
    echo "Error: Benchmark folder not specified"
    exit 1
}

# Check if directory exists
test -d "$benchmark_folder" || {
    echo "Error: Directory '$benchmark_folder' does not exist"
    exit 1
}

# Create archive
tar -C "$benchmark_folder" -cjf "$benchmark_folder.stats.tbz" \
-T <(cd "$benchmark_folder" && find . -name '.aider.*')
