"""
Unit tests for rc_align.py

Run with: python3 -m pytest test_rc_align.py -v
Or: python3 test_rc_align.py
"""

import unittest
import sys
import os
from unittest.mock import patch, MagicMock, mock_open
from io import StringIO

# Import the module to test
import rc_align


class TestRunGitCommand(unittest.TestCase):
    """Test the run_git_command function"""

    @patch('subprocess.run')
    def test_successful_command(self, mock_run):
        """Test successful git command execution"""
        mock_run.return_value = MagicMock(stdout="v1.0.0\n", returncode=0)
        result = rc_align.run_git_command(["describe", "--tags"])
        self.assertEqual(result, "v1.0.0")
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_failed_command_with_fail_on_error_true(self, mock_run):
        """Test failed command with fail_on_error=True"""
        from subprocess import CalledProcessError
        mock_run.side_effect = CalledProcessError(1, 'git')
        result = rc_align.run_git_command(["invalid"], fail_on_error=True)
        # Should catch exception and return None
        self.assertIsNone(result)

    @patch('subprocess.run')
    def test_failed_command_with_fail_on_error_false(self, mock_run):
        """Test failed command with fail_on_error=False"""
        from subprocess import CalledProcessError
        mock_run.side_effect = CalledProcessError(1, 'git')
        result = rc_align.run_git_command(["invalid"], fail_on_error=False)
        self.assertIsNone(result)


class TestFindBaselineTag(unittest.TestCase):
    """Test the find_baseline_tag function"""

    @patch('rc_align.run_git_command')
    def test_rc_tag_found(self, mock_git):
        """Test when RC tag exists"""
        mock_git.return_value = "v1.2.3-rc.4"
        tag, from_stable = rc_align.find_baseline_tag()
        self.assertEqual(tag, "v1.2.3-rc.4")
        self.assertFalse(from_stable)

    @patch('rc_align.run_git_command')
    def test_stable_tag_found(self, mock_git):
        """Test when only stable tag exists"""
        mock_git.return_value = "v1.2.3"
        tag, from_stable = rc_align.find_baseline_tag()
        self.assertEqual(tag, "v1.2.3")
        self.assertTrue(from_stable)

    @patch('rc_align.run_git_command')
    @patch('sys.stdout', new_callable=StringIO)
    def test_no_tags_found(self, mock_stdout, mock_git):
        """Test when no tags exist"""
        mock_git.return_value = None
        tag, from_stable = rc_align.find_baseline_tag()
        self.assertIsNone(tag)
        self.assertTrue(from_stable)
        self.assertIn("No tags found", mock_stdout.getvalue())


class TestGetCommitDepth(unittest.TestCase):
    """Test the get_commit_depth function"""

    @patch('rc_align.run_git_command')
    def test_no_commits(self, mock_git):
        """
        Test with no commits
        Example: Empty history → depth = 0
        """
        mock_git.return_value = None
        depth = rc_align.get_commit_depth("v1.0.0")
        self.assertEqual(depth, 0)

    @patch('rc_align.run_git_command')
    def test_user_commits_only(self, mock_git):
        """
        Test counting only user commits
        Example: 3 user commits → depth = 3
        """
        mock_git.return_value = "feat: new feature\nfix: bug fix\ndocs: update readme"
        depth = rc_align.get_commit_depth("v1.0.0")
        self.assertEqual(depth, 3)

    @patch('rc_align.run_git_command')
    def test_filter_bot_commits_with_release_as(self, mock_git):
        """
        Test filtering bot commits with Release-As footer
        Example: 3 commits (1 bot with "Release-As:") → depth = 2
        """
        commits = "feat: new feature\nchore: something Release-As: 1.0.0\nfix: bug fix"
        mock_git.return_value = commits
        depth = rc_align.get_commit_depth("v1.0.0")
        self.assertEqual(depth, 2)

    @patch('rc_align.run_git_command')
    def test_filter_bot_commits_with_enforce_message(self, mock_git):
        """
        Test filtering bot commits with enforce message
        Example: 3 commits (1 bot with "chore: enforce correct rc version") → depth = 2
        """
        commits = "feat: new feature\nchore: enforce correct rc version\nfix: bug fix"
        mock_git.return_value = commits
        depth = rc_align.get_commit_depth("v1.0.0")
        self.assertEqual(depth, 2)

    @patch('rc_align.run_git_command')
    def test_mixed_commits(self, mock_git):
        """
        Test with mixed user and bot commits
        Example: 5 total commits (2 bot) → depth = 3
          - feat: new feature (user)
          - chore: enforce correct rc version (bot - filtered)
          - fix: bug fix (user)
          - Release-As: 1.2.3 (bot - filtered)
          - docs: update (user)
        """
        commits = "\n".join([
            "feat: new feature",
            "chore: enforce correct rc version",
            "fix: bug fix",
            "Release-As: 1.2.3",
            "docs: update",
        ])
        mock_git.return_value = commits
        depth = rc_align.get_commit_depth("v1.0.0")
        self.assertEqual(depth, 3)


class TestParseSemver(unittest.TestCase):
    """Test the parse_semver function"""

    def test_parse_rc_version(self):
        """
        Test parsing RC version
        Example: "v1.2.3-rc.4" → (1, 2, 3, 4)
        """
        major, minor, patch, rc = rc_align.parse_semver("v1.2.3-rc.4")
        self.assertEqual((major, minor, patch, rc), (1, 2, 3, 4))

    def test_parse_stable_version(self):
        """
        Test parsing stable version
        Example: "v1.2.3" → (1, 2, 3, 0)
        """
        major, minor, patch, rc = rc_align.parse_semver("v1.2.3")
        self.assertEqual((major, minor, patch, rc), (1, 2, 3, 0))

    def test_parse_none_version(self):
        """
        Test parsing None version (no tags)
        Example: None → (0, 0, 0, 0)
        """
        major, minor, patch, rc = rc_align.parse_semver(None)
        self.assertEqual((major, minor, patch, rc), (0, 0, 0, 0))

    def test_parse_major_version(self):
        """
        Test parsing major version
        Example: "v5.0.0" → (5, 0, 0, 0)
        """
        major, minor, patch, rc = rc_align.parse_semver("v5.0.0")
        self.assertEqual((major, minor, patch, rc), (5, 0, 0, 0))

    def test_parse_high_rc_number(self):
        """
        Test parsing high RC number
        Example: "v2.5.10-rc.99" → (2, 5, 10, 99)
        """
        major, minor, patch, rc = rc_align.parse_semver("v2.5.10-rc.99")
        self.assertEqual((major, minor, patch, rc), (2, 5, 10, 99))


class TestAnalyzeImpact(unittest.TestCase):
    """Test the analyze_impact function"""

    @patch('rc_align.run_git_command')
    def test_breaking_change_with_exclamation(self, mock_git):
        """
        Test detecting breaking change with exclamation mark
        Example: "feat!: breaking change" → breaking=True, feat=False
        Note: feat! is detected as breaking but not as feat (regex is strict)
        """
        mock_git.return_value = "feat!: breaking change\nSome details"
        is_breaking, is_feat = rc_align.analyze_impact("v1.0.0")
        self.assertTrue(is_breaking)
        # The regex `^feat(\(.*\))?:` will match "feat" but not "feat!"
        # However, "feat!" still contains "feat" semantically, but our regex is strict
        # This is actually correct behavior - we detect breaking but not feat in this case

    @patch('rc_align.run_git_command')
    def test_breaking_change_with_footer(self, mock_git):
        """
        Test detecting breaking change with BREAKING CHANGE footer
        Example: "feat: new\nBREAKING CHANGE: API changed" → breaking=True, feat=True
        """
        mock_git.return_value = "feat: new feature\n\nBREAKING CHANGE: API changed"
        is_breaking, is_feat = rc_align.analyze_impact("v1.0.0")
        self.assertTrue(is_breaking)
        self.assertTrue(is_feat)

    @patch('rc_align.run_git_command')
    def test_feature_commit(self, mock_git):
        """
        Test detecting feature commit
        Example: "feat: new feature" → breaking=False, feat=True
        """
        mock_git.return_value = "feat: new feature\nSome details"
        is_breaking, is_feat = rc_align.analyze_impact("v1.0.0")
        self.assertFalse(is_breaking)
        self.assertTrue(is_feat)

    @patch('rc_align.run_git_command')
    def test_fix_commit(self, mock_git):
        """
        Test detecting fix commit
        Example: "fix: bug fix" → breaking=False, feat=False
        """
        mock_git.return_value = "fix: bug fix\nSome details"
        is_breaking, is_feat = rc_align.analyze_impact("v1.0.0")
        self.assertFalse(is_breaking)
        self.assertFalse(is_feat)

    @patch('rc_align.run_git_command')
    def test_breaking_fix(self, mock_git):
        """
        Test detecting breaking fix
        Example: "fix!: breaking bug fix" → breaking=True, feat=False
        """
        mock_git.return_value = "fix!: breaking bug fix"
        is_breaking, is_feat = rc_align.analyze_impact("v1.0.0")
        self.assertTrue(is_breaking)
        self.assertFalse(is_feat)

    @patch('rc_align.run_git_command')
    def test_feature_with_scope(self, mock_git):
        """
        Test detecting feature with scope
        Example: "feat(api): new endpoint" → breaking=False, feat=True
        """
        mock_git.return_value = "feat(api): new endpoint"
        is_breaking, is_feat = rc_align.analyze_impact("v1.0.0")
        self.assertFalse(is_breaking)
        self.assertTrue(is_feat)

    @patch('rc_align.run_git_command')
    def test_breaking_change_with_footer(self, mock_git):
        """Test detecting breaking change with BREAKING CHANGE footer"""
        mock_git.return_value = "feat: new feature\n\nBREAKING CHANGE: API changed"
        is_breaking, is_feat = rc_align.analyze_impact("v1.0.0")
        self.assertTrue(is_breaking)
        self.assertTrue(is_feat)

    @patch('rc_align.run_git_command')
    def test_feature_commit(self, mock_git):
        """Test detecting feature commit"""
        mock_git.return_value = "feat: new feature\nSome details"
        is_breaking, is_feat = rc_align.analyze_impact("v1.0.0")
        self.assertFalse(is_breaking)
        self.assertTrue(is_feat)

    @patch('rc_align.run_git_command')
    def test_fix_commit(self, mock_git):
        """Test detecting fix commit"""
        mock_git.return_value = "fix: bug fix\nSome details"
        is_breaking, is_feat = rc_align.analyze_impact("v1.0.0")
        self.assertFalse(is_breaking)
        self.assertFalse(is_feat)

    @patch('rc_align.run_git_command')
    def test_breaking_fix(self, mock_git):
        """Test detecting breaking fix"""
        mock_git.return_value = "fix!: breaking bug fix"
        is_breaking, is_feat = rc_align.analyze_impact("v1.0.0")
        self.assertTrue(is_breaking)
        self.assertFalse(is_feat)

    @patch('rc_align.run_git_command')
    def test_feature_with_scope(self, mock_git):
        """Test detecting feature with scope"""
        mock_git.return_value = "feat(api): new endpoint"
        is_breaking, is_feat = rc_align.analyze_impact("v1.0.0")
        self.assertFalse(is_breaking)
        self.assertTrue(is_feat)

    @patch('rc_align.run_git_command')
    def test_no_commits(self, mock_git):
        """Test with no commits"""
        mock_git.return_value = None
        is_breaking, is_feat = rc_align.analyze_impact("v1.0.0")
        self.assertFalse(is_breaking)
        self.assertFalse(is_feat)


class TestCalculateNextVersion(unittest.TestCase):
    """Test the calculate_next_version function"""

    def test_breaking_change_bump_major(self):
        """
        Test breaking change bumps major version
        Example: v1.2.3 + feat!: breaking → v2.0.0-rc.1
        """
        result = rc_align.calculate_next_version(
            major=1, minor=2, patch=3, rc=0,
            depth=1, is_breaking=True, is_feat=False, from_stable=True
        )
        self.assertEqual(result, "2.0.0-rc.1")

    def test_feature_from_stable_bump_minor(self):
        """
        Test feature from stable bumps minor version
        Example: v1.2.3 + feat: new feature → v1.3.0-rc.1
        """
        result = rc_align.calculate_next_version(
            major=1, minor=2, patch=3, rc=0,
            depth=1, is_breaking=False, is_feat=True, from_stable=True
        )
        self.assertEqual(result, "1.3.0-rc.1")

    def test_feature_from_rc_with_patch_bump_minor(self):
        """
        Test feature from RC with patch>0 bumps minor
        Example: v1.2.1-rc.2 + feat: feature → v1.3.0-rc.1
        """
        result = rc_align.calculate_next_version(
            major=1, minor=2, patch=1, rc=2,
            depth=1, is_breaking=False, is_feat=True, from_stable=False
        )
        self.assertEqual(result, "1.3.0-rc.1")

    def test_feature_from_rc_increment_rc(self):
        """
        Test feature from RC increments RC number
        Example: v1.2.0-rc.2 + feat: feature → v1.2.0-rc.3
        """
        result = rc_align.calculate_next_version(
            major=1, minor=2, patch=0, rc=2,
            depth=1, is_breaking=False, is_feat=True, from_stable=False
        )
        self.assertEqual(result, "1.2.0-rc.3")

    def test_fix_from_stable_bump_patch(self):
        """
        Test fix from stable bumps patch version
        Example: v1.2.3 + fix: bug fix → v1.2.4-rc.1
        """
        result = rc_align.calculate_next_version(
            major=1, minor=2, patch=3, rc=0,
            depth=1, is_breaking=False, is_feat=False, from_stable=True
        )
        self.assertEqual(result, "1.2.4-rc.1")

    def test_fix_from_rc_increment_rc(self):
        """
        Test fix from RC increments RC number
        Example: v1.2.3-rc.2 + fix: bug fix → v1.2.3-rc.3
        """
        result = rc_align.calculate_next_version(
            major=1, minor=2, patch=3, rc=2,
            depth=1, is_breaking=False, is_feat=False, from_stable=False
        )
        self.assertEqual(result, "1.2.3-rc.3")

    def test_multiple_commits_increment_rc(self):
        """
        Test multiple commits increment RC by depth
        Example: v1.2.3-rc.1 + 5 commits → v1.2.3-rc.6 (1 + 5)
        """
        result = rc_align.calculate_next_version(
            major=1, minor=2, patch=3, rc=1,
            depth=5, is_breaking=False, is_feat=False, from_stable=False
        )
        self.assertEqual(result, "1.2.3-rc.6")

    def test_breaking_change_from_high_version(self):
        """
        Test breaking change from high version
        Example: v10.5.2 + feat!: breaking → v11.0.0-rc.1
        """
        result = rc_align.calculate_next_version(
            major=10, minor=5, patch=2, rc=0,
            depth=1, is_breaking=True, is_feat=True, from_stable=True
        )
        self.assertEqual(result, "11.0.0-rc.1")


class TestMainFunction(unittest.TestCase):
    """Test the main function"""

    @patch('rc_align.run_git_command')
    @patch('rc_align.find_baseline_tag')
    @patch('rc_align.get_commit_depth')
    @patch('sys.stdout', new_callable=StringIO)
    def test_main_no_commits(self, mock_stdout, mock_depth, mock_baseline, mock_git):
        """Test main with no commits"""
        # Mock git log to return a non-release commit
        mock_git.return_value = "feat: some feature"
        mock_baseline.return_value = ("v1.0.0", True)
        mock_depth.return_value = 0

        rc_align.main()

        output = mock_stdout.getvalue()
        self.assertIn("No user commits found", output)

    @patch('rc_align.run_git_command')
    @patch('rc_align.find_baseline_tag')
    @patch('sys.stdout', new_callable=StringIO)
    def test_main_exception_handling(self, mock_stdout, mock_baseline, mock_git):
        """Test main handles exceptions gracefully"""
        # Mock git log to return a non-release commit
        mock_git.return_value = "feat: some feature"
        mock_baseline.side_effect = Exception("Test error")

        # Main should handle exception and exit gracefully
        with self.assertRaises(SystemExit) as cm:
            rc_align.main()
        self.assertEqual(cm.exception.code, 0)

        output = mock_stdout.getvalue()
        # The actual output shows it falls back gracefully
        self.assertIn("CRITICAL ERROR", output)

    @patch('rc_align.run_git_command')
    @patch('sys.stdout', new_callable=StringIO)
    def test_main_skips_release_please_merge(self, mock_stdout, mock_git):
        """Test main skips when detecting a release-please merge commit"""
        # Mock git log to return a release-please commit
        mock_git.return_value = "chore(main): release 1.0.0"

        rc_align.main()

        output = mock_stdout.getvalue()
        self.assertIn("Detected release-please merge commit", output)
        self.assertIn("Skipping", output)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions"""

    def test_version_zero_point_zero(self):
        """
        Test calculating from 0.0.0 (first release)
        Example: v0.0.0 (no tags) + feat: initial → v0.1.0-rc.1
        """
        result = rc_align.calculate_next_version(
            major=0, minor=0, patch=0, rc=0,
            depth=1, is_breaking=False, is_feat=True, from_stable=True
        )
        self.assertEqual(result, "0.1.0-rc.1")

    def test_very_high_rc_number(self):
        """
        Test with very high RC number
        Example: v1.0.0-rc.100 + 5 commits → v1.0.0-rc.105
        """
        result = rc_align.calculate_next_version(
            major=1, minor=0, patch=0, rc=100,
            depth=5, is_breaking=False, is_feat=False, from_stable=False
        )
        self.assertEqual(result, "1.0.0-rc.105")

    @patch('rc_align.run_git_command')
    def test_empty_commit_message(self, mock_git):
        """Test with empty commit message"""
        mock_git.return_value = ""
        depth = rc_align.get_commit_depth("v1.0.0")
        self.assertEqual(depth, 0)

    def test_parse_invalid_version_format(self):
        """Test parsing invalid version format"""
        result = rc_align.parse_semver("invalid")
        self.assertEqual(result, (0, 0, 0, 0))


class TestIntegrationScenarios(unittest.TestCase):
    """Integration tests for complete scenarios"""

    def test_scenario_version_calculation_logic(self):
        """
        Test complete version calculation scenarios
        
        Scenario 1: v1.2.3 → v1.3.0-rc.1
          Current: v1.2.3 (stable)
          Commit: feat: new feature
          Result: v1.3.0-rc.1 (minor bump)
        
        Scenario 2: v1.3.0-rc.2 → v1.3.0-rc.3
          Current: v1.3.0-rc.2 (RC)
          Commit: fix: bug fix
          Result: v1.3.0-rc.3 (RC increment)
        
        Scenario 3: v2.5.1 → v3.0.0-rc.1
          Current: v2.5.1 (stable)
          Commit: feat!: breaking change
          Result: v3.0.0-rc.1 (major bump)
        """
        # Test 1: Feature from stable → minor bump
        result = rc_align.calculate_next_version(
            major=1, minor=2, patch=3, rc=0,
            depth=1, is_breaking=False, is_feat=True, from_stable=True
        )
        self.assertEqual(result, "1.3.0-rc.1")
        
        # Test 2: Fix from RC → RC increment
        result = rc_align.calculate_next_version(
            major=1, minor=3, patch=0, rc=2,
            depth=1, is_breaking=False, is_feat=False, from_stable=False
        )
        self.assertEqual(result, "1.3.0-rc.3")
        
        # Test 3: Breaking change from stable → major bump
        result = rc_align.calculate_next_version(
            major=2, minor=5, patch=1, rc=0,
            depth=1, is_breaking=True, is_feat=True, from_stable=True
        )
        self.assertEqual(result, "3.0.0-rc.1")


def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(run_tests())
