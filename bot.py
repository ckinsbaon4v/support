import os
import json
import subprocess
import requests

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

def search_keywords(repo, keywords):
    print(f"Searching for keywords in {repo}...")
    # Clone the repo shallowly to search
    temp_dir = f"temp_{repo.replace('/', '_')}"
    run_command(f"git clone --depth 1 https://github.com/{repo}.git {temp_dir}")
    
    matches = []
    for keyword in keywords:
        # Use grep to find keywords
        grep_output = run_command(f"grep -rnE \"{keyword}\" {temp_dir} --exclude-dir=.git")
        if grep_output:
            for line in grep_output.split('\n'):
                parts = line.split(':', 2)
                if len(parts) >= 3:
                    file_path = parts[0].replace(f"{temp_dir}/", "")
                    line_number = parts[1]
                    context = parts[2].strip()
                    matches.append({
                        "keyword": keyword,
                        "file_path": file_path,
                        "line_number": line_number,
                        "context": context
                    })
    
    # Cleanup
    run_command(f"rm -rf {temp_dir}")
    return matches

def issue_exists(repo, title):
    # Check if an issue with the same title already exists to avoid duplicates
    output = run_command(f"gh issue list --repo {repo} --search \"{title}\" --json title")
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
        matches = search_keywords(repo, config['keywords'])
        for match in matches:
            create_issue_and_comment(repo, match, config)

if __name__ == "__main__":
    main()
