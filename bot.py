import os
import json
import subprocess

def load_config():
    with open('config.json', 'r') as f:
        return json.load(f)

def run_command(command):
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error: {e.stderr}")
        return None

def main():
    config = load_config()
    gh_token = os.getenv("GH_TOKEN")
    
    if not gh_token:
        print("Error: GH_TOKEN is not set.")
        return

    for repo in config['repositories']:
        print(f"Scanning {repo}...")
        for keyword in config['keywords']:
            # Search for the keyword in the repository code
            # We limit to recently updated files to keep it fast
            search_query = f"gh search code \"{keyword}\" --repo {repo} --json path,url"
            search_results = run_command(search_query)
            
            if not search_results:
                continue
                
            try:
                files = json.loads(search_results)
                for file in files:
                    file_path = file['path']
                    issue_title = f"{config['issue_title_prefix']} {keyword} found in {file_path}"
                    
                    # Check if issue already exists
                    check_issue = run_command(f"gh issue list --repo {repo} --search \"{issue_title}\" --state open --json number")
                    if check_issue and len(json.loads(check_issue)) > 0:
                        print(f"Issue already exists for {file_path}")
                        continue
                    
                    # Create the issue
                    print(f"Creating issue for {keyword} in {file_path}...")
                    body = config['issue_body_template'].format(
                        keyword=keyword,
                        file_path=file_path,
                        line_number="N/A",
                        context=f"Keyword detected in {file_path}"
                    )
                    
                    issue_num = run_command(f"gh issue create --repo {repo} --title \"{issue_title}\" --body \"{body}\" --label \"{config['issue_labels']}\" --json number --jq .number")
                    
                    if issue_num:
                        # Add the auto-reply comment
                        run_command(f"gh issue comment {issue_num} --repo {repo} --body \"{config['comment_body']}\"")
            except Exception as e:
                print(f"Error processing {keyword} in {repo}: {e}")

if __name__ == "__main__":
    main()

