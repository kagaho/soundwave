#!/usr/bin/env python3
"""Offline source validation, never a cluster deployability claim."""
from pathlib import Path
import ast
import json
import re
import subprocess
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
errors = []
counts = {'python': 0, 'yaml': 0, 'json': 0, 'shell': 0, 'javascript': 0}
blocked_names = {'credentials.json', 'auth.json', 'token.json', 'gcp-oauth.keys.json', 'kubeconfig'}
secret_patterns = [
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(r'(?:tvly-|hf_|ghp_|github_pat_|nvapi-)[A-Za-z0-9_-]{20,}'),
    re.compile(r'[#?]token=[A-Za-z0-9_-]{20,}'),
]

def error(path, message):
    errors.append(f'{path.relative_to(ROOT)}: {message}')

for p in sorted(ROOT.rglob('*')):
    rel = p.relative_to(ROOT)
    if any(part in {'.git', '.venv', 'venv', 'node_modules', '__pycache__'} for part in rel.parts):
        continue
    if not p.is_file():
        continue
    if (p.name in blocked_names or p.suffix in {'.key', '.pem', '.p12', '.pfx', '.crt'}
            or (p.name.startswith('.env') and p.name != '.env.example')
            or (p.name.endswith('-token.json'))):
        error(p, 'private file must not be included')
    try:
        text = p.read_text()
    except UnicodeError:
        continue
    if any(pattern.search(text) for pattern in secret_patterns):
        error(p, 'credential-like content; run Gitleaks for a redacted report')
    try:
        if p.suffix == '.py':
            ast.parse(text, filename=str(rel))
            counts['python'] += 1
        elif p.suffix in {'.yaml', '.yml'} or p.name.endswith(('.yaml.example', '.yml.example')):
            docs = list(yaml.safe_load_all(text))
            counts['yaml'] += 1
            for doc in docs:
                if not isinstance(doc, dict) or not doc.get('apiVersion'):
                    continue
                if doc.get('kind') == 'Secret' and not p.name.endswith('.example'):
                    error(p, 'Kubernetes Secret belongs in a .example template')
                if any(k in doc.get('metadata', {}) for k in ['uid','resourceVersion','creationTimestamp','managedFields']):
                    error(p, 'generated Kubernetes metadata must be removed')
                if 'status' in doc:
                    error(p, 'generated Kubernetes status must be removed')
                if doc.get('kind') == 'Deployment' and doc.get('metadata',{}).get('name') == 'hermes':
                    spec=doc['spec']
                    pod=spec['template']['spec']
                    if spec.get('strategy',{}).get('type') != 'Recreate':
                        error(p,'Hermes host-local PVC needs Recreate strategy')
                    if not pod.get('nodeSelector',{}).get('kubernetes.io/hostname'):
                        error(p,'Hermes host-local PVC needs a node selector')
                    for container in pod.get('containers',[]):
                        sc=container.get('securityContext',{})
                        if not sc.get('runAsNonRoot') or sc.get('allowPrivilegeEscalation') is not False:
                            error(p,'Hermes must run nonroot without privilege escalation')
        elif p.suffix == '.json':
            json.loads(text)
            counts['json'] += 1
        elif p.suffix == '.sh':
            subprocess.run(['bash','-n',str(p)],check=True,capture_output=True)
            counts['shell'] += 1
        elif p.suffix == '.js':
            subprocess.run(['node','--check',str(p)],check=True,capture_output=True)
            counts['javascript'] += 1
    except (SyntaxError, ValueError, yaml.YAMLError, subprocess.CalledProcessError) as exc:
        error(p, f'{type(exc).__name__}: syntax/structure validation failed')

# Validate navigation maintained for the clean release. Historical prose contains
# command examples and links to external tools that need human review.
active_docs = [ROOT/x for x in ['README.md','SECURITY.md','CONTRIBUTING.md','THIRD_PARTY_NOTICES.md','docs/releases/RELEASING.md']]
active_docs += [ROOT/x for x in ['hermes/README.md','ASR/README.md','deployments/README.md','integrations/hermes-llm-wiki-obsidian/README.md'] if (ROOT/x).exists()]
for p in active_docs:
    for href in re.findall(r'\]\(([^\s)]+)\)',p.read_text()):
        if '://' in href or href.startswith(('#','mailto:')):
            continue
        target=href.split('#')[0]
        if target and not (p.parent/target).exists():
            error(p,'broken local link: '+target)

test = ROOT/'oauth/generate-tokens.test.js'
if test.exists():
    r=subprocess.run(['node','--test',str(test)],cwd=test.parent,capture_output=True,text=True)
    if r.returncode:
        errors.append('OAuth callback security tests failed')
        print(r.stdout)
        print(r.stderr,file=sys.stderr)
    else:
        print('OAuth callback security tests passed')
if (ROOT/'tests/test_helpers.py').exists():
    r=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests'],cwd=ROOT,capture_output=True,text=True)
    if r.returncode:
        errors.append('Helper behavior tests failed')
        print(r.stdout)
        print(r.stderr,file=sys.stderr)
    else:
        print('Helper behavior tests passed')
print('Validated:', ', '.join(f'{v} {k}' for k,v in counts.items()))
if errors:
    print('\n'.join(errors),file=sys.stderr)
    sys.exit(1)
print('Static checks passed. Runtime and publication review remain separate.')
