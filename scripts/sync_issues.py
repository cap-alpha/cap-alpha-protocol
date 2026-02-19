
import os
import re
import subprocess
import json

ISSUE_FILE = "docs/project_management/ISSUES_BACKLOG.md"

def get_existing_issues():
    """Fetches all issues (open and closed) to check for duplicates."""
    print("Fetching existing GitHub issues...")
    cmd = ["gh", "issue", "list", "--state", "all", "--limit", "100", "--json", "title,number,state"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error fetching issues: {e.stderr}")
        return []

def parse_issues(file_path):
    with open(file_path, 'r') as f:
        content = f.read()

    # Split by "## " headers
    issue_blocks = re.split(r'\n## ', content)
    parsed_issues = []

    for block in issue_blocks:
        if "**Title**:" not in block:
            continue
        
        lines = block.split('\n')
        title = ""
        labels = ""
        body_lines = []
        in_body = False

        for line in lines:
            if line.startswith("**Title**:"):
                title = line.replace("**Title**:", "").strip()
                # Remove [Tag] from title for cleaner matching if needed, but keeping strict for now
            elif line.startswith("**Labels**:"):
                labels = line.replace("**Labels**:", "").strip()
            elif line.startswith("**Body**:"):
                in_body = True
            elif in_body:
                body_lines.append(line)
        
        if title:
            parsed_issues.append({
                "title": title,
                "labels": labels,
                "body": "\n".join(body_lines).strip()
            })

    return parsed_issues

def sync_issue(issue, existing_issues):
    # Check if issue exists by Title
    match = next((i for i in existing_issues if i['title'] == issue['title']), None)
    
    if match:
        # UPDATE
        print(f"Updating issue #{match['number']}: {issue['title']}...")
        cmd = [
            "gh", "issue", "edit", str(match['number']),
            "--body", issue['body']
        ]
        # Basic label handling (add new ones, doesn't remove old ones easily via CLI without replace)
        if issue['labels']:
             for label in issue['labels'].split(','):
                clean = label.strip()
                if clean:
                    cmd.extend(["--add-label", clean])

        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"Updated #{match['number']}")
        except subprocess.CalledProcessError as e:
            print(f"Error updating #{match['number']}: {e.stderr}")
    else:
        # CREATE
        print(f"Creating issue: {issue['title']}...")
        cmd = [
            "gh", "issue", "create",
            "--title", issue['title'],
            "--body", issue['body']
        ]
        
        if issue['labels']:
            for label in issue['labels'].split(','):
                clean = label.strip()
                if clean:
                    cmd.extend(["--label", clean])
        
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"Created new issue.")
        except subprocess.CalledProcessError as e:
            print(f"Error creating issue: {e.stderr}")

if __name__ == "__main__":
    if not os.path.exists(ISSUE_FILE):
        print(f"File not found: {ISSUE_FILE}")
        exit(1)

    gh_issues = get_existing_issues()
    local_issues = parse_issues(ISSUE_FILE)
    
    print(f"Found {len(local_issues)} local issues in markdown.")
    
    for issue in local_issues:
        sync_issue(issue, gh_issues)
