import os
import re
import subprocess
import sys
from typing import Tuple, Optional, List

# Constants
BOT_COMMIT_MSG = "chore: enforce correct rc version"
BOT_FOOTER_TAG = "Release-As:"
# Standard release-please bot patterns
IGNORE_PATTERNS = [
    r"^chore\(.*\): release",
    r"^chore: release",
    r"^chore: reset manifest to stable version"
]

class VersionCalculator:
    def __init__(self):
        self.branch = os.environ.get("GITHUB_REF_NAME", "unknown")

    def run_git(self, args: List[str], fail_on_error=True) -> Optional[str]:
        """Executes a git command and returns stripped output."""
        try:
            result = subprocess.run(
                ["git"] + args, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True, 
                check=fail_on_error
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            if fail_on_error:
                print(f"ERROR: Git command failed: {' '.join(args)}\n{e.stderr}")
                sys.exit(1)
            return None

    def parse_semver(self, tag: str) -> Tuple[int, int, int, int, bool]:
        """
        Parses a tag into (major, minor, patch, rc, is_stable).
        Returns (0,0,0,0,True) if invalid.
        """
        if not tag:
            return 0, 0, 0, 0, True

        # Regex for v1.0.0 or v1.0.0-rc.1
        # Group 4 is the RC number (optional)
        match = re.match(r"^v(\d+)\.(\d+)\.(\d+)(?:-rc\.(\d+))?$", tag)
        
        if match:
            major = int(match.group(1))
            minor = int(match.group(2))
            patch = int(match.group(3))
            rc_part = match.group(4)
            
            if rc_part:
                return major, minor, patch, int(rc_part), False
            else:
                return major, minor, patch, 0, True
        
        return 0, 0, 0, 0, True

    def get_latest_tag(self) -> Tuple[Optional[str], bool]:
        """
        Finds the most relevant tag reachable from HEAD.
        Returns (tag_string, is_stable_boolean).
        """
        raw_tags = self.run_git(["tag", "-l", "v*", "--merged", "HEAD"], fail_on_error=False)
        
        if not raw_tags:
            print("INFO: No tags found. Assuming fresh baseline (0.0.0).")
            return None, True

        all_tags = raw_tags.split('\n')

        # Sort Logic: Major > Minor > Patch > Stable > RC
        def sort_key(t):
            maj, min, pat, rc, is_stable = self.parse_semver(t)
            # We want Stable (1) to come AFTER RC (0) in ascending sort, 
            # so usually Stable > RC. But here we sort Reverse, so Stable comes first.
            return (maj, min, pat, 1 if is_stable else 0, rc)

        sorted_tags = sorted(all_tags, key=sort_key, reverse=True)
        best_tag = sorted_tags[0]
        
        _, _, _, _, is_stable = self.parse_semver(best_tag)
        
        print(f"INFO: Baseline tag found: {best_tag} (Stable: {is_stable})")
        return best_tag, is_stable

    def get_commit_depth_and_impact(self, baseline_tag: str) -> Tuple[int, bool, bool]:
        """
        Calculates commit depth (excluding bots) and analyzes impact (feat/breaking).
        Returns (depth, is_breaking, is_feat).
        """
        rev_range = f"{baseline_tag}..HEAD" if baseline_tag else "HEAD"
        print(f"INFO: Analyzing range: {rev_range}")

        # Get full subjects for filtering
        logs = self.run_git(["log", rev_range, "--first-parent", "--pretty=format:%s|||%B"])
        if not logs:
            return 0, False, False

        entries = logs.split('\n')
        
        valid_commits = []
        is_breaking = False
        is_feat = False

        for entry in entries:
            parts = entry.split("|||")
            subject = parts[0]
            body = parts[1] if len(parts) > 1 else ""
            full_msg = f"{subject}\n{body}"

            # 1. Filtering Logic
            if BOT_FOOTER_TAG in full_msg or BOT_COMMIT_MSG in subject:
                continue
            
            is_bot = False
            for pattern in IGNORE_PATTERNS:
                if re.match(pattern, subject):
                    is_bot = True
                    break
            if is_bot:
                continue

            # 2. Impact Analysis
            valid_commits.append(subject)
            
            # Check Breaking
            if "BREAKING CHANGE" in full_msg or re.search(r"^(feat|fix|refactor)(\(.*\))?!:", subject):
                is_breaking = True
            
            # Check Feat
            if re.search(r"^feat(\(.*\))?:", subject):
                is_feat = True

        print(f"INFO: Found {len(valid_commits)} user commits since baseline.")
        return len(valid_commits), is_breaking, is_feat

    def calculate_next(self, current_tag: str, is_stable_baseline: bool) -> str:
        maj, min, pat, rc, _ = self.parse_semver(current_tag)
        depth, is_breaking, is_feat = self.get_commit_depth_and_impact(current_tag)

        if depth == 0:
            print("INFO: No changes detected. Exiting.")
            sys.exit(0)

        # Logic Mapping to Flowchart
        # 1. Breaking Change -> Major Bump
        if is_breaking:
            return f"{maj + 1}.0.0-rc.{depth}"

        # 2. Feature -> Minor Bump (if stable) OR Stay on RC
        if is_feat:
            if is_stable_baseline:
                # v1.0.0 -> v1.1.0-rc.X
                return f"{maj}.{min + 1}.0-rc.{depth}"
            else:
                # v1.1.0-rc.1 -> v1.1.0-rc.X (Keep same minor, increment RC)
                return f"{maj}.{min}.{pat}-rc.{rc + depth}"

        # 3. Fix/Other -> Patch Bump (if stable) OR Stay on RC
        if is_stable_baseline:
            # v1.0.0 -> v1.0.1-rc.X
            return f"{maj}.{min}.{pat + 1}-rc.{depth}"
        else:
            # v1.0.1-rc.1 -> v1.0.1-rc.X
            return f"{maj}.{min}.{pat}-rc.{rc + depth}"

    def run(self):
        print(f"INFO: Processing Branch: {self.branch}")

        # --- BRANCH: MAIN (Stable Promotion) ---
        if self.branch in ["main", "master"]:
            tag, _ = self.get_latest_tag()
            if tag:
                clean_ver = re.sub(r'-rc.*', '', tag).lstrip('v')
                print(f"OUTPUT: next_version={clean_ver}")
                with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                    f.write(f"next_version={clean_ver}\n")
            return

        # --- BRANCH: NEXT (RC Calculation) ---
        tag, is_stable = self.get_latest_tag()
        next_ver = self.calculate_next(tag, is_stable)
        
        print(f"OUTPUT: next_version={next_ver}")
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"next_version={next_ver}\n")

if __name__ == "__main__":
    VersionCalculator().run()
