#!/usr/bin/env python3
"""One real SSH/UI flow against a prepared isolated server; no physical-input claim."""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid

repo = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('control', repo/'mainline/gaming-shell/control.py')
control = importlib.util.module_from_spec(spec); spec.loader.exec_module(control)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--host', required=True)
parser.add_argument('--port', type=int, required=True)
parser.add_argument('--identity', type=Path, required=True)
parser.add_argument('--known-hosts', type=Path, required=True)
parser.add_argument('--binary', required=True)
parser.add_argument('--evidence', type=Path, required=True)
parser.add_argument('--keyboard', action='store_true')
args = parser.parse_args()


def request(op='observe', **values):
    return {'version':1, 'id':str(uuid.uuid4()), 'op':op, 'screenshot':False, **values}


def exchange(req, known=None, identity=None):
    result = control.ssh_exchange(args.host, args.port, identity or args.identity, known or args.known_hosts, req)
    assert result['binary_sha256'] == args.binary
    return result


initial = exchange(request(screenshot=True))
assert initial['state']['page'] == 0 and initial['state']['selected'] == 0
control.save_result(args.evidence, copy.deepcopy(initial))
changed = exchange(request('tap', action='right', session=initial['session'], sequence=initial['sequence'],
                           binary_sha256=args.binary, screenshot=True))
assert changed['state']['selected'] == 1 and changed['sequence'] == initial['sequence']+1
assert changed['capture']['sha256'] != initial['capture']['sha256']
control.save_result(args.evidence, copy.deepcopy(changed))
try:
    exchange(request('tap', action='right', session=initial['session'], sequence=initial['sequence'], binary_sha256=args.binary))
except control.ControlError as error:
    assert 'stale_sequence' in str(error)
else:
    raise AssertionError('Stale action was accepted')

cache = repo/'mainline/out/.cache'
with tempfile.TemporaryDirectory(prefix='ssh key ', dir=cache) as temporary:
    root = Path(temporary)
    identity = root/'identity'; known = root/'known hosts'
    shutil.copy2(args.identity, identity); shutil.copy2(args.known_hosts, known)
    assert exchange(request(), known, identity)['sequence'] == changed['sequence']
    wrong = root/'wrong host'
    public = Path(str(args.identity)+'.pub').read_text().split()
    wrong.write_text(f'[{args.host}]:{args.port} {public[0]} {public[1]}\n'); wrong.chmod(0o600)
    try:
        exchange(request(), wrong)
    except control.ControlError:
        pass
    else:
        raise AssertionError('Wrong SSH host identity was accepted')

ssh = ['/usr/bin/ssh','-F','/dev/null','-T','-p',str(args.port),'-i',str(args.identity),
       '-o','IdentityAgent=none','-o','IdentitiesOnly=yes','-o','BatchMode=yes',
       '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(args.known_hosts),
       '-o','GlobalKnownHostsFile=/dev/null','-o','ConnectTimeout=3']
forbidden = subprocess.run([*ssh,'ark@'+args.host,'printf R46H_UNRESTRICTED_SHELL'], input=b'{}\n', capture_output=True, timeout=8)
assert forbidden.returncode != 0 and b'R46H_UNRESTRICTED_SHELL' not in forbidden.stdout
forward = subprocess.run([*ssh,'-o','ExitOnForwardFailure=yes','-N','-R','0:127.0.0.1:1','ark@'+args.host], capture_output=True, timeout=8)
assert forward.returncode != 0
assert exchange(request())['sequence'] == changed['sequence']
ended = exchange(request('tap', action='left', session=changed['session'], sequence=changed['sequence'], binary_sha256=args.binary))
assert ended['state']['selected'] == 0
if args.keyboard:
    current = ended
    def tap(action, screenshot=False):
        global current
        current=exchange(request('tap', action=action, session=current['session'], sequence=current['sequence'],
                                 binary_sha256=args.binary, screenshot=screenshot))
        return current['state']
    tap('nextTab'); tap('nextTab')
    for _ in range(8): tap('down')
    tap('right'); tap('down'); tap('accept')
    assert current['state']['testInputVisible']
    tap('down'); tap('accept',True)
    assert control.checked_image(copy.deepcopy(current))
    control.save_result(args.evidence,copy.deepcopy(current))
    tap('erase',True); control.save_result(args.evidence,copy.deepcopy(current))
    assert not tap('submit')['editing']
    tap('home'); tap('accept'); tap('favorite',True)
    assert current['state']['editing'] and current['state']['sensitiveVisible']
    assert current['capture']['status']=='sensitive_entry'
    tap('back')
report = {'status':'SSH_UI_FLOW_PASS','binary':args.binary,
          'checks':['real SSH screenshots and action','stale action rejected','wrong host key rejected',
                    'paths with spaces','arbitrary command rejected','forwarding rejected'],
          'keyboard_test_capture':args.keyboard,
          'boundary':'isolated server and Qt app; R46H transport/physical inputs untested'}
args.evidence.mkdir(parents=True, exist_ok=True)
(args.evidence/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
