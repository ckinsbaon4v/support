import os
import json
import subprocess
from datetime import datetime, timedelta

def load_config():
    with open('config.json', 'r') as f:
        return json.load(f)

def run_command(command):
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {command}\n{e.stderr}")
        return None

def get_recent_changes(repo, keywords):
    print(f"Checking for recent changes in {repo}...")
    
    # Calculate the timestamp for 1 hour ago
    since_time = (datetime.utcnow() - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
    
    # Get commits in the last hour
    commits_json = run_command(f"gh api repos/{repo}/commits --method GET -f since={since_time}")
    if not commits_json:
        return []
    
    commits = json.loads(commits_json)
    if not commits:
        print(f"No recent commits found in {repo}.")
        return []

    matches = []
    processed_files = set()

    for commit in commits:
        sha = commit['sha']
        # Get the files changed in this commit
        commit_details_json = run_command(f"gh api repos/{repo}/commits/{sha}")
        if not commit_details_json:
            continue
        
        commit_details = json.loads(commit_details_json)
        for file in commit_details.get('files', []):
            file_path = file['filename']
            # Avoid processing the same file multiple times in one run
            if file_path in processed_files:
                continue
            
            # Get the file content at this commit
            # We use 'gh api' to get content to avoid cloning
            content_json = run_command(f"gh api repos/{repo}/contents/{file_path}?ref={sha}")
            if not content_json:
                continue
            
            try:
                content_data = json.loads(content_json)
                if 'content' not in content_data:
                    continue
                
                import base64
                content = base64.b64decode(content_data['content']).decode('utf-8', errors='ignore')
                
                lines = content.splitlines()
                for i, line in enumerate(lines):
                    for keyword in keywords:
                        if keyword in line:
                            matches.append({
                                "keyword": keyword,
                                "file_path": file_path,
                                "line_number": i + 1,
                                "context": line.strip(),
                                "sha": sha
                            })
                processed_files.add(file_path)
            except Exception as e:
                print(f"Error processing file {file_path}: {e}")
                
    return matches

def issue_exists(repo, title):
    # Check if an issue with the same title already exists
    output = run_command(f"gh issue list --repo {repo} --search \"{title}\" --state open --json title")
    if output:
        issues = json.loads(output)
        return any(issue['title'] == title for issue in issues)
    return False

def create_issue_and_comment(repo, match, config):
    title = f"{config['issue_title_prefix']} {match['keyword']} found in {match['file_path']}"
    
    if issue_exists(repo, title):
        print(f"Issue already exists: {title}")
        return

    body = config['issue_body_template'].format(
        keyword=match['keyword'],
        file_path=match['file_path'],
        line_number=match['line_number'],
        context=match['context']
    )
    # Add a link to the specific commit
    body += f"\n\n**Commit SHA:** [{match['sha'][:7]}](https://github.com/{repo}/commit/{match['sha']})"
    
    print(f"Creating issue in {repo}: {title}")
    issue_number = run_command(f"gh issue create --repo {repo} --title \"{title}\" --body \"{body}\" --label \"{config['issue_labels']}\" --json number --jq .number")
    
    if issue_number:
        print(f"Created issue #{issue_number}. Adding comment...")
        run_command(f"gh issue comment {issue_number} --repo {repo} --body \"{config['comment_body']}\"")

def main():
    if not os.getenv("GH_TOKEN"):
        print("Error: GH_TOKEN environment variable not set.")
        return

    config = load_config()
    for repo in config['repositories']:
        matches = get_recent_changes(repo, config['keywords'])
        for match in matches:
            create_issue_and_comment(repo, match, config)

if __name__ == "__main__":
    main()

