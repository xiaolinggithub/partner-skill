from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class InstallTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / 'home'
        self.source = self.root / 'source'
        self.source.mkdir()
        shutil.copy2(ROOT / 'install.sh', self.source / 'install.sh')
        for name in ('SKILL.md', 'scripts/partner-config.py', 'scripts/partner-tryout.py',
                     'idea-king/SKILL.md', 'idea-king/codex-prompt.md'):
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('new payload\n')
        self.dest = self.home / '.agents/skills/partner-skill'
        self.env = {**os.environ, 'HOME': str(self.home)}

    def install(self, *args, source=None):
        return subprocess.run(['bash', str((source or self.source) / 'install.sh'),
                               '--target', 'agents', *args], env=self.env,
                              capture_output=True, text=True, timeout=20)

    def old_install(self, path=None):
        path = path or self.dest
        path.mkdir(parents=True)
        (path / 'SKILL.md').write_text('old local edits\n')
        (path / 'local-only').write_text('preserve in backup\n')

    def stub(self, command, body):
        folder = self.root / 'bin'
        folder.mkdir(exist_ok=True)
        executable = folder / command
        executable.write_text('#!/bin/sh\n' + body)
        executable.chmod(0o755)
        self.env['PATH'] = str(folder) + os.pathsep + os.environ['PATH']

    def assert_old_untouched(self, path=None):
        path = path or self.dest
        self.assertEqual((path / 'SKILL.md').read_text(), 'old local edits\n')
        self.assertTrue((path / 'local-only').exists())
        self.assertEqual(list(path.parent.glob(path.name + '.stage.*')), [])

    def test_fresh_install_and_upgrade_keep_old_local_files_in_backup(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.dest / 'SKILL.md').read_text(), 'new payload\n')
        self.assertIn('host=generic', (self.dest / '.install-meta').read_text())
        (self.dest / 'local-only').write_text('retain me')
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        backups = list(self.dest.parent.glob(self.dest.name + '.backup.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'local-only').read_text(), 'retain me')
        self.assertFalse((self.dest / 'local-only').exists())

    def test_linked_targets_upgrade_real_directory_once_and_preserve_links(self):
        self.old_install()
        links = []
        for host in ('.codex', '.claude'):
            path = self.home / host / 'skills/partner-skill'
            path.parent.mkdir(parents=True)
            path.symlink_to('../../.agents/skills/partner-skill')
            links.append(path)
        idea = self.home / '.agents/skills/idea-king'
        idea.symlink_to('partner-skill/idea-king')
        companion = self.home / '.claude/skills/idea-king'
        companion.symlink_to('../../.agents/skills/idea-king')
        result = self.install('--target', 'all')
        self.assertEqual(result.returncode, 0, result.stderr)
        for path in links:
            self.assertEqual(os.readlink(path), '../../.agents/skills/partner-skill')
            self.assertEqual((path / 'SKILL.md').read_text(), 'new payload\n')
        self.assertEqual(os.readlink(idea), 'partner-skill/idea-king')
        self.assertTrue((idea / 'codex-prompt.md').exists())
        self.assertEqual(os.readlink(companion), '../../.agents/skills/idea-king')
        backups = list(self.dest.parent.glob(self.dest.name + '.backup.*'))
        self.assertEqual(len(backups), 1)
        self.assert_old_untouched(backups[0])

    def test_install_from_source_alias_never_moves_the_source(self):
        self.dest.parent.mkdir(parents=True)
        self.dest.symlink_to(self.source)
        alias = self.root / 'source-alias'
        alias.symlink_to(self.source)
        result = self.install('--target', 'all', source=alias)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.dest.is_symlink())
        self.assertEqual((self.source / 'SKILL.md').read_text(), 'new payload\n')
        self.assertEqual(list(self.root.glob('source.backup.*')), [])
        self.assertTrue((self.home / '.codex/skills/partner-skill/SKILL.md').exists())

    def test_dangling_link_is_filled_without_replacing_link(self):
        self.dest.parent.mkdir(parents=True)
        target = self.root / 'missing/real-skill'
        self.dest.symlink_to(target)
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(os.readlink(self.dest)), target)
        self.assertEqual((target / 'SKILL.md').read_text(), 'new payload\n')

    def test_dry_run_leaves_no_directories_or_metadata(self):
        result = self.install('--target', 'all', '--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.home.exists())

    def test_copy_failure_leaves_original_and_existing_backups_untouched(self):
        self.old_install()
        backup = self.dest.with_name(self.dest.name + '.backup.saved')
        backup.mkdir()
        self.stub('tar', 'exit 71\n')
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assert_old_untouched()
        self.assertTrue(backup.is_dir())

    def test_incomplete_payload_fails_before_moving_old_install(self):
        self.old_install()
        (self.source / 'scripts/partner-config.py').unlink()
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assert_old_untouched()
        self.assertEqual(list(self.dest.parent.glob(self.dest.name + '.backup.*')), [])

    def test_failed_replace_restores_old_directory_and_keeps_alias(self):
        target = self.root / 'installed'
        self.old_install(target)
        self.dest.parent.mkdir(parents=True)
        self.dest.symlink_to(target)
        self.stub('mv', 'case "$1" in */payload) exit 73;; esac\nexec /bin/mv "$@"\n')
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assert_old_untouched(target)
        self.assertEqual(Path(os.readlink(self.dest)), target)

    def test_parent_directory_symlink_stays_intact(self):
        skills = self.home / '.agents/skills'
        skills.parent.mkdir(parents=True)
        real = self.root / 'shared-skills'
        real.mkdir()
        skills.symlink_to(real)
        self.old_install(real / 'partner-skill')
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(skills.is_symlink())
        self.assertEqual((real / 'partner-skill/SKILL.md').read_text(), 'new payload\n')
        self.assertEqual(len(list(real.glob('partner-skill.backup.*'))), 1)

    def test_git_payload_excludes_untracked_scratch_files(self):
        for args in (['init', '-q'], ['add', '.'],
                     ['-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                      '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture']):
            subprocess.run(['git', '-C', str(self.source), *args], env=self.env,
                           check=True, capture_output=True)
        (self.source / 'scratch.txt').write_text('do not install')
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.dest / 'scratch.txt').exists())
        self.assertNotIn('source_commit=unknown', (self.dest / '.install-meta').read_text())

    def test_overlapping_source_and_target_are_rejected_without_moving_source(self):
        self.dest.parent.mkdir(parents=True)
        self.dest.symlink_to(self.root)
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.source / 'install.sh').exists())
        self.assertTrue(self.dest.is_symlink())


if __name__ == '__main__':
    unittest.main()
