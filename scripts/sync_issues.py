import os
import re
import json
import subprocess
import urllib.request
from datetime import datetime, timezone

SPRINT_PLAN_FILE = "docs/sprints/MASTER_SPRINT_PLAN.md"
REPO = "ucalegon206/cap-alpha-protocol"
STATE_FILE = ".sync_state.json"

def run_cmd(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running {' '.join(cmd)}:\n{e.stderr}")
        return None

def fetch_all_issues():
    print("Fetching GitHub issues...")
    output = run_cmd(["gh", "issue", "list", "--repo", REPO, "--state", "all", "--limit", "300", "--json", "title,number,state,comments,url,createdAt,updatedAt"])
    if output:
        return json.loads(output)
    return []

def get_slack_webhook():
    env_file = ".env"
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                if line.startswith("SLACK_WEBHOOK_URL="):
                    return line.strip().split("=", 1)[1].strip('"\'')
    return None

def notify_slack(message):
    webhook_url = get_slack_webhook()
    if not webhook_url:
        print("No Slack webhook URL found in .env, skipping notification.")
        return
    
    data = json.dumps({"text": message}).encode('utf-8')
    req = urllib.request.Request(webhook_url, data=data, headers={'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req)
        print("Slack notification sent successfully.")
    except Exception as e:
        print(f"Error sending Slack notification: {e}")

def get_last_sync_time():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
            return data.get("last_sync_time", "1970-01-01T00:00:00Z")
    # Default to 1 hour ago if no state exists
    return "1970-01-01T00:00:00Z"

def set_last_sync_time(time_str):
    with open(STATE_FILE, "w") as f:
        json.dump({"last_sync_time": time_str}, f)

def main():
    if not os.path.exists(SPRINT_PLAN_FILE):
        print(f"File not found: {SPRINT_PLAN_FILE}")
        return

    last_sync_time = get_last_sync_time()
    # Format current time to match GitHub's ISO 8601 UTC format
    current_sync_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    issues = fetch_all_issues()
    
    issues_by_tag = {}
    for issue in issues:
        # Check if the issue itself is brand new
        issue_created_at = issue.get("createdAt", "")
        if issue_created_at > last_sync_time:
            msg = f"🆕 *New Issue Created!* #{issue['number']}: {issue['title']}\nURL: {issue['url']}"
            notify_slack(msg)

        # Process comments
        comments_field = issue.get("comments", [])
        if isinstance(comments_field, list):
            for comment in comments_field:
                comment_time = comment.get("createdAt", "")
                if comment_time > last_sync_time:
                    author = comment.get("author", {}).get("login", "Someone")
                    body = comment.get("body", "")
                    url = comment.get("url", issue.get("url"))
                    # Only notify if it's a message from the user, or notify for all new comments
                    msg = f"💬 *New Comment* on Issue #{issue['number']} by {author}:\n> {body}\nURL: {url}"
                    notify_slack(msg)

        match = re.search(r"\[(SP[0-9.]+-.*?)\]", issue["title"])
        if match:
            tag = match.group(1)
            issues_by_tag[tag] = issue

    with open(SPRINT_PLAN_FILE, "r") as f:
        content = f.read()

    new_lines = []
    
    for line in content.split("\n"):
        match = re.search(r"^(\s*)-\s+\[(.*?)\]\s+(SP[0-9.]+-.*?):\s*(.*)", line)
        
        # If the line is an injected comment (starts with `  - 💬`), strip it out so we can refresh them
        if "💬" in line:
            continue
            
        if match:
            indent = match.group(1)
            old_state = match.group(2)
            tag = match.group(3)
            
            # The desc might already contain the (GH-#X) suffix if we ran this script previously.
            desc = match.group(4)
            desc = re.sub(r"\s+\(GH-#\d+\)$", "", desc)
            
            if tag in issues_by_tag:
                issue = issues_by_tag[tag]
                gh_state = issue["state"]
                num = issue["number"]
                
                if gh_state == "CLOSED":
                    new_bracket = "x"
                else: 
                    new_bracket = old_state if old_state in [" ", "/"] else " "
                    
                new_line = f"{indent}- [{new_bracket}] {tag}: {desc} (GH-#{num})"
                new_lines.append(new_line)
                
                comments_field = issue.get("comments")
                comment_count = 0
                if isinstance(comments_field, int):
                    comment_count = comments_field
                elif isinstance(comments_field, dict): 
                    comment_count = comments_field.get("totalCount", 0)
                elif isinstance(comments_field, list):
                    comment_count = len(comments_field)
                    
                if comment_count > 0:
                    new_lines.append(f"{indent}  - 💬 **{comment_count} comment(s)** on GitHub. See {issue['url']}")
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
            
    with open(SPRINT_PLAN_FILE, "w") as f:
        f.write("\n".join(new_lines))
        
    set_last_sync_time(current_sync_time)
    print(f"Successfully synced latest GitHub states into {SPRINT_PLAN_FILE}!")

if __name__ == "__main__":
    main()
