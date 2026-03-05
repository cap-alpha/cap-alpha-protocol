import os
import re
import shutil
from collections import defaultdict

def reorganize_data():
    # Running inside an ephemeral docker container mapped to /app
    project_root = "/app"
    data_dir = os.path.join(project_root, "data")
    archive_dir = os.path.join(data_dir, "archive")
    redownload_file = os.path.join(data_dir, "redownload_list.txt")
    
    dirs_to_scan = [
        os.path.join(data_dir, "raw"),
        os.path.join(data_dir, "bronze")
    ]
    
    print(f"Scanning directories: {dirs_to_scan}")
    
    os.makedirs(archive_dir, exist_ok=True)
    
    # Make the regex more forgiving. We just want everything BEFORE the trailing timestamp.
    # Spotrac files end with things like _20260201_173723.csv or _20251218_110954.csv 
    # Let's match: (anything) _ (8digits) _ (6digits) . (ext)
    file_pattern = re.compile(r"^(.*?)_(\d{8}_\d{6})\.(\w+)$")
    
    redownload_symbols = set()
    files_moved = 0
    
    for scan_dir in dirs_to_scan:
        if not os.path.exists(scan_dir):
            continue
            
        for root, _, files in os.walk(scan_dir):
            # Group files by their base symbol
            file_groups = defaultdict(list)
            
            for file in files:
                match = file_pattern.match(file)
                if match:
                    base_symbol = match.group(1)
                    file_groups[base_symbol].append({
                        "filename": file,
                        "filepath": os.path.join(root, file),
                        "timestamp": match.group(2)
                    })
            
            # Process groups
            for base_symbol, versions in file_groups.items():
                if len(versions) > 1:
                    print(f"Duplicate collision detected for: {base_symbol} ({len(versions)} files)")
                    redownload_symbols.add(base_symbol)
                    
                    # Move ALL conflicting versions to archive to ensure pipeline doesn't read dirty state
                    for v in versions:
                        src_path = v["filepath"]
                        # Prepend the relative directory path to avoid filename collisions in the archive root
                        rel_path = os.path.relpath(root, data_dir).replace("/", "_")
                        dest_filename = f"{rel_path}_{v['filename']}"
                        dest_path = os.path.join(archive_dir, dest_filename)
                        
                        print(f"  -> Archiving: {v['filename']}")
                        shutil.move(src_path, dest_path)
                        files_moved += 1

    # Write the redownload list
    if redownload_symbols:
        with open(redownload_file, "a") as f:
            for symbol in sorted(list(redownload_symbols)):
                f.write(f"{symbol}\n")
                
    print(f"\nReorganization complete.")
    print(f"Files safely archived: {files_moved}")
    print(f"Symbols added to redownload list: {len(redownload_symbols)}")

if __name__ == "__main__":
    reorganize_data()
