"""Exercise release helpers with a fake kubectl; never contact a cluster."""
from pathlib import Path
import importlib.util
import os
import subprocess
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
WIKI=ROOT/'integrations/hermes-llm-wiki-obsidian'
FAKE_KUBECTL='''#!/usr/bin/env python3
import os, subprocess, sys
args=sys.argv[1:]
if 'get' in args:
    print(os.environ.get('FAKE_POD','hermes-fixture'),end='')
elif 'exec' in args:
    cmd=args[args.index('--')+1:]
    raise SystemExit(subprocess.run(cmd).returncode)
else:
    raise SystemExit('Unexpected kubectl command')
'''

class HelperTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='soundwave-helper-')
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        tools=self.base/'bin'
        tools.mkdir()
        (tools/'kubectl').write_text(FAKE_KUBECTL)
        (tools/'kubectl').chmod(0o755)
        self.env={**os.environ,'PATH':str(tools)+os.pathsep+os.environ['PATH'],
            'WIKI_PATH':str(self.base/'vault with spaces'), 'HERMES_HOME':str(self.base/'hermes home')}

    def run_script(self, script, **overrides):
        return subprocess.run(['bash',str(script)],env={**self.env,**overrides},capture_output=True,text=True)

    @unittest.skipUnless(WIKI.exists(),'Wiki integration starts at 2.1.0')
    def test_install_preserves_existing_notes_and_reset_changes_only_selection(self):
        script=WIKI/'scripts/install-wiki.sh'
        first=self.run_script(script)
        self.assertEqual(first.returncode,0,first.stderr)
        vault=Path(self.env['WIKI_PATH'])
        for name in ['SCHEMA.md','index.md','log.md','_registry/active-context.yaml','_registry/wiki-registry.yaml']:
            self.assertTrue((vault/name).is_file())
        (vault/'SCHEMA.md').write_text('existing private schema')
        registry=(vault/'_registry/wiki-registry.yaml').read_bytes()
        (vault/'_registry/active-context.yaml').write_text('include: [private-domain]\n')
        second=self.run_script(script)
        self.assertEqual(second.returncode,0,second.stderr)
        self.assertEqual((vault/'SCHEMA.md').read_text(),'existing private schema')
        reset=self.run_script(WIKI/'scripts/reset-wiki-context.sh')
        self.assertEqual(reset.returncode,0,reset.stderr)
        self.assertEqual((vault/'_registry/active-context.yaml').read_bytes(),(WIKI/'templates/active-context.yaml').read_bytes())
        self.assertEqual((vault/'_registry/wiki-registry.yaml').read_bytes(),registry)
        for skill in ['wiki-context','wiki-ingest','wiki-query']:
            self.assertTrue((Path(self.env['HERMES_HOME'])/'skills/wiki'/skill/'SKILL.md').is_file())

    @unittest.skipUnless(WIKI.exists(),'Wiki integration starts at 2.1.0')
    def test_missing_pod_does_not_write_vault(self):
        result=self.run_script(WIKI/'scripts/install-wiki.sh',FAKE_POD='')
        self.assertNotEqual(result.returncode,0)
        self.assertFalse(Path(self.env['WIKI_PATH']).exists())

    @unittest.skipUnless(WIKI.exists(),'Wiki integration starts at 2.1.0')
    def test_epub_spine_order_and_source_preservation(self):
        spec=importlib.util.spec_from_file_location('epub_converter',WIKI/'scripts/epub-to-md.py')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        source=self.base/'book.epub'
        with zipfile.ZipFile(source,'w') as z:
            z.writestr('META-INF/container.xml','<container><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>')
            z.writestr('OPS/book.opf','<package><manifest><item id="one" href="one.xhtml" media-type="application/xhtml+xml"/><item id="two" href="two.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="two"/><itemref idref="one"/></spine></package>')
            z.writestr('OPS/one.xhtml','<h1>First</h1><p>A &amp; B</p><script>hidden()</script>')
            z.writestr('OPS/two.xhtml','<h1>Second</h1><p>Visible</p>')
        before=source.read_bytes()
        out=self.base/'raw/book.md'
        self.assertEqual(module.convert(source,out),2)
        text=out.read_text()
        self.assertLess(text.index('# Second'),text.index('# First'))
        self.assertIn('A & B',text)
        self.assertNotIn('hidden()',text)
        self.assertEqual(source.read_bytes(),before)

    @unittest.skipUnless((ROOT/'hermes/scripts/sync-to-pod.sh').exists(),'Hermes integration starts at 2.0.0')
    def test_workspace_sync_excludes_untracked_and_private_memory(self):
        repo=self.base/'repo'
        hermes=repo/'hermes'
        scripts=hermes/'scripts'
        scripts.mkdir(parents=True)
        script=scripts/'sync-to-pod.sh'
        script.write_bytes((ROOT/'hermes/scripts/sync-to-pod.sh').read_bytes())
        (hermes/'README.md').write_text('public reference')
        memory=hermes/'hermes-config/memories'
        memory.mkdir(parents=True)
        (memory/'USER.md').write_text('private user data')
        (memory/'USER.md.example').write_text('neutral example')
        subprocess.run(['git','init','-q',str(repo)],check=True)
        subprocess.run(['git','-C',str(repo),'add','.'],check=True)
        (hermes/'.env').write_text('private untracked configuration')
        workspace=self.base/'workspace with spaces'
        result=self.run_script(script,WORKSPACE=str(workspace))
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual((workspace/'README.md').read_text(),'public reference')
        self.assertTrue((workspace/'hermes-config/memories/USER.md.example').exists())
        self.assertFalse((workspace/'hermes-config/memories/USER.md').exists())
        self.assertFalse((workspace/'.env').exists())
        self.assertFalse((workspace/'scripts').exists())

if __name__=='__main__':
    unittest.main()
