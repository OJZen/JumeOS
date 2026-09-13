#!/usr/bin/env python3
"""Run the actual lease recovery and power-exit blocks against task-owned fixtures."""
from pathlib import Path
import os,subprocess,tempfile
repo=Path(__file__).resolve().parents[2]
lease_source=(repo/'mainline/gaming-shell/device-lease.sh').read_text()
restore=lease_source[lease_source.index('restore() {'):lease_source.index('if [[ $1 == --restore')]
probe=(repo/'mainline/gaming-shell/probe-r46h.sh').read_text()
cleanup=probe[probe.index('restore() {'):probe.index('trap restore EXIT')]
with tempfile.TemporaryDirectory(prefix='device-lease-',dir=repo/'mainline/out/.cache') as tmp:
    base=Path(tmp)
    script=base/'restore.sh'
    script.write_text('''set -Eeuo pipefail
lease=$FIXTURE/lease
unit=${TEST_UNIT:-}
cpu=$FIXTURE/cpu
light=$FIXTURE/brightness
nodes=("$light" "$cpu/scaling_min_freq" "$cpu/scaling_max_freq" "$cpu/scaling_governor")
cat() {
    if [[ $1 == /proc/sys/kernel/random/boot_id ]]; then echo fixture-boot
    elif [[ $1 == "$cpu/scaling_max_freq" ]]; then
        local count;count=$(command cat "$FIXTURE/read-count");count=$((count+1));echo "$count" > "$FIXTURE/read-count"
        if (( count <= 2 )); then echo 1200000; else command cat "$@"; fi
    else command cat "$@"; fi
}
stat() { if [[ $3 == "$lease" ]]; then echo 0:0:700; else command cat "$3.meta"; fi; }
chown() { local mode; mode=$(command cat "$2.meta"); echo "$1:${mode##*:}" > "$2.meta"; }
chmod() { local value; value=$(command cat "$2.meta"); echo "${value%:*}:$1" > "$2.meta"; }
''' + restore + '\nrestore\n')
    for minimum,maximum in [(816000,1200000),(1200000,1296000)]:
        trial=base/str(minimum);(trial/'lease').mkdir(parents=True);(trial/'cpu').mkdir()
        (trial/'read-count').write_text('0\n')
        (trial/'lease/ready').touch();(trial/'lease/boot').write_text('fixture-boot\n')
        (trial/'lease/unit').write_text('r46h-shell-probe-123.service\n')
        names=['brightness','cpu/scaling_min_freq','cpu/scaling_max_freq','cpu/scaling_governor']
        for i,(name,old,current) in enumerate(zip(names,['80','600000','1296000','schedutil'],['20',str(minimum),str(maximum),'performance'])):
            (trial/name).write_text(current+'\n');Path(str(trial/name)+'.meta').write_text('1000:1000:600\n')
            (trial/f'lease/{i}.value').write_text(old+'\n');(trial/f'lease/{i}.mode').write_text('0:0:644\n')
        result=subprocess.run(['/bin/bash',str(script)],env={**os.environ,'FIXTURE':str(trial),'TEST_UNIT':'r46h-wayland-probe-456.service'},capture_output=True,text=True,timeout=5)
        assert result.returncode==1 and (trial/'lease').exists(),result
        assert (trial/'brightness').read_text().strip()=='20', 'Wrong unit modified the active lease'
        result=subprocess.run(['/bin/bash',str(script)],env={**os.environ,'FIXTURE':str(trial),'TEST_UNIT':'r46h-shell-probe-123.service'},capture_output=True,text=True,timeout=5)
        assert result.returncode==0,result.stderr
        assert not (trial/'lease').exists()
        assert [(trial/p).read_text().strip() for p in names]==['80','600000','1296000','schedutil']
        assert all(Path(str(trial/p)+'.meta').read_text().strip()=='0:0:644' for p in names)
    for status,mode,power_ok,expected_power in [(77,1,0,True),(78,1,0,True),(77,0,0,False),(0,1,0,False),(77,1,1,False)]:
        scope=base/f'power-{status}-{mode}-{power_ok}';scope.mkdir()
        (scope/'device-lease.sh').write_text('#!/bin/sh\necho LEASE_RESTORED\n')
        code='''set -Eeuo pipefail
unit=fixture
saved_mux=
systemctl() { echo "CALL $*"; if [[ $1 == --no-block ]]; then return "$POWER_OK"; fi; return 0; }
sync() { echo SYNC; }
''' + cleanup + '\ntrap restore EXIT\nexit "$STATUS"\n'
        result=subprocess.run(['/bin/bash','-c',code],env={**os.environ,'scope':str(scope),'mode':'--device' if mode else '--run','device_mode':str(mode),'STATUS':str(status),'POWER_OK':str(power_ok)},capture_output=True,text=True,timeout=5)
        assert ('power_request=' in result.stdout)==expected_power,result
        assert ('CALL start r46h-gaming-frontend.service' in result.stdout)!=expected_power,result
        assert result.returncode==(0 if expected_power else 1 if power_ok else status),result
print('DEVICE_LEASE_CHECK PASS: recovery values/permissions and gated power exit; host fixtures only')
