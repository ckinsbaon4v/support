import os
import json
import subprocess
import base64
from datetime import datetime, timedelta

def load_config():
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"DEBUG: Error loading config.json: {e}")
        return None

def run_command(command):
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"DEBUG: Error running command: {command}\n{e.stderr}")
        return None

def get_recent_changes(repo, keywords):
    print(f"DEBUG: Checking for recent changes in {repo}...")
    
    # Widening the window to 24 hours for debugging to ensure we catch something
    since_time = (datetime.utcnow() - timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M:%SZ')
    print(f"DEBUG: Searching for commits since {since_time}...")
    
    # Get commits in the last 24 hours
    commits_json = run_command(f"gh api repos/{repo}/commits --method GET -f since={since_time}")
    if not commits_json:
        print(f"DEBUG: No commits found or API error for {repo}.")
        return []
    
    try:
        commits = json.loads(commits_json)
    except Exception as e:
        print(f"DEBUG: Error parsing commits JSON for {repo}: {e}")
        return []

    if not commits:
        print(f"DEBUG: No recent commits found in {repo} for the last 24 hours.")
        return []

    print(f"DEBUG: Found {len(commits)} commits in the last 24 hours.")
    matches = []
    processed_files = set()

    for commit in commits:
        sha = commit['sha']
        print(f"DEBUG: Processing commit {sha[:7]}...")
        
        # Get the files changed in this commit
        commit_details_json = run_command(f"gh api repos/{repo}/commits/{sha}")
        if not commit_details_json:
            print(f"DEBUG: Could not get details for commit {sha[:7]}.")
            continue
        
        try:
            commit_details = json.loads(commit_details_json)
        except Exception as e:
            print(f"DEBUG: Error parsing commit details for {sha[:7]}: {e}")
            continue

        for file in commit_details.get('files', []):
            file_path = file['filename']
            if file_path in processed_files:
                continue
            
            print(f"DEBUG: Checking file: {file_path}")
            
            # Get the file content at this commit
            content_json = run_command(f"gh api repos/{repo}/contents/{file_path}?ref={sha}")
            if not content_json:
                print(f"DEBUG: Could not get content for {file_path} at {sha[:7]}.")
                continue
            
            try:
                content_data = json.loads(content_json)
                if 'content' not in content_data:
                    print(f"DEBUG: No 'content' field in API response for {file_path}.")
                    continue
                
                content = base64.b64decode(content_data['content']).decode('utf-8', errors='ignore')
                
                lines = content.splitlines()
                for i, line in enumerate(lines):
                    for keyword in keywords:
                        if keyword in line:
                            print(f"DEBUG: MATCH FOUND! Keyword '{keyword}' in {file_path} at line {i+1}.")
                            matches.append({
                                "keyword": keyword,
                                "file_path": file_path,
                                "line_number": i + 1,
                                "context": line.strip(),
                                "sha": sha
                            })
                processed_files.add(file_path)
            except Exception as e:
                print(f"DEBUG: Error processing file {file_path}: {e}")
                
    return matches

def issue_exists(repo, title):
    # Check if an issue with the same title already exists
    output = run_command(f"gh issue list --repo {repo} --search \"{title}\" --state open --json title")
    if output:
        try:
            issues = json.loads(output)
            exists = any(issue['title'] == title for issue in issues)
            if exists:
                print(f"DEBUG: Issue already exists with title: {title}")
            return exists
        except Exception as e:
            print(f"DEBUG: Error parsing issue list JSON: {e}")
    return False

def create_issue_and_comment(repo, match, config):
    title = f"{config['issue_title_prefix']} {match['keyword']} found in {match['file_path']}"
    
    if issue_exists(repo, title):
        return

    body = config['issue_body_template'].format(
        keyword=match['keyword'],
        file_path=match['file_path'],
        line_number=match['line_number'],
        context=match['context']
    )
    body += f"\n\n**Commit SHA:** [{match['sha'][:7]}](https://github.com/{repo}/commit/{match['sha']})"
    
    print(f"DEBUG: Creating issue in {repo}: {title}")
    issue_number = run_command(f"gh issue create --repo {repo} --title \"{title}\" --body \"{body}\" --label \"{config['issue_labels']}\" --json number --jq .number")
    
    if issue_number:
        print(f"DEBUG: Created issue #{issue_number}. Adding comment...")
        run_command(f"gh issue comment {issue_number} --repo {repo} --body \"{config['comment_body']}\"")
    else:
        print(f"DEBUG: Failed to create issue in {repo}.")

def main():
    if not os.getenv("GH_TOKEN"):
        print("DEBUG: Error: GH_TOKEN environment variable not set.")
        return

    config = load_config()
    if not config:
        return

    for repo in config['repositories']:
        matches = get_recent_changes(repo, config['keywords'])
        if not matches:
            print(f"DEBUG: No matches found for {repo}.")
        for match in matches:
            create_issue_and_comment(repo, match, config)

if __name__ == "__main__":
    main()
