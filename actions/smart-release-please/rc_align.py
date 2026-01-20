import os
import re
import subprocess
import sys

BOT_COMMIT_MSG = "chore: enforce correct rc version"
BOT_FOOTER_TAG = "Release-As:"

def run_git_command(args, fail_on_error=True):
    try:
        result = subprocess.run(["git"] + args, stdout=subprocess.PIPE, text=True, check=fail_on_error)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None

def find_baseline_tag():
    # Get all tags sorted by creation date (most recent first)
    # This searches across ALL branches, not just ancestors of HEAD
    tags_output = run_git_command(["tag", "-l", "v*", "--sort=-creatordate"], fail_on_error=False)
    
    if not tags_output:
        print("INFO: No tags found. Assuming 0.0.0 baseline.")
        return None, True
    
    # Get the most recent tag
    tag = tags_output.split('\n')[0]

    # Check if the found tag is an RC
    if "-rc" in tag:
        print(f"INFO: Baseline found (RC): {tag}")
        return tag, False
    
    # Otherwise, it's stable
    print(f"INFO: Baseline found (Stable): {tag}")
    return tag, True

def get_commit_depth(baseline_tag):
    rev_range = f"{baseline_tag}..HEAD" if baseline_tag else "HEAD"
    
    # Get all subjects since baseline
    raw_subjects = run_git_command(["log", rev_range, "--first-parent", "--pretty=format:%s"], fail_on_error=False)
    if not raw_subjects:
        return 0

    real_commits = []
    for s in raw_subjects.split('\n'):
        # 1. Skip your alignment bot commits
        if BOT_FOOTER_TAG in s or BOT_COMMIT_MSG in s:
            continue
        
        # 2. Skip Release Please commits (CRITICAL FIX)
        # Matches "chore(next): release v1.0.0-rc.1" or "chore: release v1.0.0-rc.1"
        if re.match(r"^chore(\(.*\))?: release", s):
            continue
            
        real_commits.append(s)

    return len(real_commits)

def parse_semver(tag):
    if not tag:
        return 0, 0, 0, 0

    m_rc = re.match(r"^v(\d+)\.(\d+)\.(\d+)-rc\.(\d+)$", tag)
    if m_rc:
        return int(m_rc[1]), int(m_rc[2]), int(m_rc[3]), int(m_rc[4])

    m_stable = re.match(r"^v(\d+)\.(\d+)\.(\d+)$", tag)
    if m_stable:
        return int(m_stable[1]), int(m_stable[2]), int(m_stable[3]), 0
    
    return 0, 0, 0, 0

def analyze_impact(baseline_tag):
    rev_range = f"{baseline_tag}..HEAD" if baseline_tag else "HEAD"
    logs = run_git_command(["log", rev_range, "--pretty=format:%B"], fail_on_error=False)
    
    if not logs:
        return False, False

    breaking_regex = r"^(feat|fix|refactor)(\(.*\))?!:"
    is_breaking = re.search(breaking_regex, logs, re.MULTILINE) or "BREAKING CHANGE" in logs
    is_feat = re.search(r"^feat(\(.*\))?:", logs, re.MULTILINE)

    return bool(is_breaking), bool(is_feat)

def calculate_next_version(major, minor, patch, rc, depth, is_breaking, is_feat, from_stable):
    if is_breaking:
        return f"{major + 1}.0.0-rc.{depth}"
    
    if is_feat:
        if from_stable or patch > 0:
            return f"{major}.{minor + 1}.0-rc.{depth}"
        else:
            return f"{major}.{minor}.{patch}-rc.{rc + depth}"

    if from_stable:
        return f"{major}.{minor}.{patch + 1}-rc.{depth}"
    else:
        return f"{major}.{minor}.{patch}-rc.{rc + depth}"

def main():
    branch = os.environ.get("GITHUB_REF_NAME")

    # --- LOGIC FOR MAIN (Stable Promotion) ---
    if branch in ["main", "master"]:
        try:
            tag, _ = find_baseline_tag()
            
            if not tag:
                stable_version = "0.1.0"
            else:
                clean_tag = re.sub(r'-rc.*', '', tag)
                stable_version = clean_tag.lstrip('v')

            print(f"INFO: Detected tag {tag}, promoting to {stable_version}")

            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write(f"next_version={stable_version}\n")
            return

        except Exception as e:
            print(f"CRITICAL ERROR (stable): {e}")
            sys.exit(0)

    # --- LOGIC FOR NEXT (RC Calculation) ---
    try:
        tag, from_stable = find_baseline_tag()
        
        depth = get_commit_depth(tag)
        if depth == 0:
            print("INFO: No user commits found since baseline. Exiting.")
            return

        major, minor, patch, rc = parse_semver(tag)
        is_breaking, is_feat = analyze_impact(tag)

        next_ver = calculate_next_version(
            major, minor, patch, rc, 
            depth, is_breaking, is_feat, from_stable
        )

        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"next_version={next_ver}\n")

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        sys.exit(0)

if __name__ == "__main__":
    main()
