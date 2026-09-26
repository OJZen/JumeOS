#!/usr/bin/env python3
"""Run the actual lease recovery and power-exit blocks against task-owned fixtures."""
from pathlib import Path
import importlib.util,os,subprocess,tempfile
repo=Path(__file__).resolve().parents[2]
lease_source=(repo/'mainline/gaming-shell/device-lease.sh').read_text()
assert 'chown 1000:$(id -g ark) "$light"' in lease_source
assert 'for node in "${nodes[@]}"; do chown' not in lease_source
assert 'for node in "${nodes[@]:1}"; do chown root:root "$node";chmod 0644 "$node";done' in lease_source
spec=importlib.util.spec_from_file_location('cpu_control',repo/'mainline/gaming-shell/cpu-control.py')
cpu_control=importlib.util.module_from_spec(spec);spec.loader.exec_module(cpu_control)
restore=lease_source[lease_source.index('restore() {'):lease_source.index('if [[ $1 == --restore')]
probe=(repo/'mainline/gaming-shell/probe-r46h.sh').read_text()
cleanup=probe[probe.index('restore() {'):probe.index('trap restore EXIT')]
with tempfile.TemporaryDirectory(prefix='device-lease-',dir=repo/'mainline/out/.cache') as tmp:
    base=Path(tmp)
    script=base/'restore.sh'
    script.write_text('''set -Eeuo pipefail
lease=$FIXTURE/lease
control=$FIXTURE/control
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
stat() {
    if [[ $3 == "$lease" ]]; then echo 0:0:700
    elif [[ $3 == "$control" ]]; then echo 0:1000:750
    else command cat "$3.meta"; fi
}
id() { [[ $* == '-g ark' ]] && echo 1000; }
systemctl() { [[ $1 == stop ]] && { echo "$2" >> "$FIXTURE/stopped"; return 0; }; return 1; }
chown() { local mode; mode=$(command cat "$2.meta"); echo "$1:${mode##*:}" > "$2.meta"; }
chmod() { local value; value=$(command cat "$2.meta"); echo "${value%:*}:$1" > "$2.meta"; }
''' + restore + '\nrestore\n')
    for minimum,maximum in [(816000,1200000),(1200000,1296000)]:
        trial=base/str(minimum);(trial/'lease').mkdir(parents=True);(trial/'cpu').mkdir()
        (trial/'control').mkdir()
        (trial/'read-count').write_text('0\n')
        (trial/'lease/ready').touch();(trial/'lease/boot').write_text('fixture-boot\n')
        (trial/'lease/unit').write_text('r46h-shell-probe-123.service\n')
        (trial/'lease/helper.unit').write_text('r46h-shell-probe-123-cpu.service\n')
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
        assert not (trial/'control').exists()
        assert (trial/'stopped').read_text().strip()=='r46h-shell-probe-123-cpu.service'
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
    root=base/'policy';lease=base/'policy-lease';lease.mkdir()
    def put(relative,value):
        path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(str(value)+'\n')
    cpu=cpu_control.CPU
    for name,value in {'scaling_min_freq':600000,'scaling_max_freq':1008000,'scaling_governor':'schedutil',
                       'scaling_available_frequencies':'600000 816000 1008000 1200000',
                       'scaling_available_governors':'schedutil performance','cpuinfo_min_freq':600000,
                       'cpuinfo_max_freq':1200000}.items():put(cpu/name,value)
    for name,value in {'sys/class/power_supply/rk817-charger/online':0,
                       'sys/class/power_supply/rk817-battery/voltage_avg':3800000,
                       'sys/class/power_supply/rk817-battery/voltage_min_design':3000000,
                       'sys/class/thermal/thermal_zone0/temp':60000,
                       'sys/class/thermal/thermal_zone0/trip_point_0_type':'hot',
                       'sys/class/thermal/thermal_zone0/trip_point_0_temp':90000}.items():put(Path(name),value)
    for index,value in ((1,600000),(2,1008000),(3,'schedutil')):(lease/f'{index}.value').write_text(str(value)+'\n')
    for scene,maximum in (('desktop',816000),('game',1008000),('off',600000)):
        assert cpu_control.apply({'op':'scene','scene':scene},root,lease)=={'ok':True}
        assert (root/cpu/'scaling_max_freq').read_text().strip()==str(maximum)
    assert cpu_control.apply({'op':'scene','scene':[]},root,lease)['error']=='invalid_request'
    manual={'op':'manual','governor':'performance','minimum':600000,'maximum':1200000}
    assert cpu_control.apply(manual,root,lease)['error']=='unsafe_supply'
    assert (root/cpu/'scaling_max_freq').read_text().strip()=='600000'
    put(Path('sys/class/power_supply/rk817-charger/online'),1)
    assert cpu_control.apply(manual,root,lease)=={'ok':True}
    assert cpu_control.apply({'op':'scene','scene':'desktop'},root,lease)['error']=='unsupported_cpu_policy'
    assert cpu_control.apply({'op':'manual','governor':'schedutil','minimum':600000,'maximum':1008000},root,lease)=={'ok':True}
    put(Path('sys/class/power_supply/rk817-battery/voltage_avg'),2900000)
    assert cpu_control.apply({'op':'scene','scene':'desktop'},root,lease)['error']=='unsafe_supply'
    assert (root/cpu/'scaling_max_freq').read_text().strip()=='1008000'
    put(Path('sys/class/power_supply/rk817-battery/voltage_avg'),3800000)
    original_write=cpu_control.write
    writes=[0]
    def interrupted(root,path,value):
        writes[0]+=1
        if writes[0]==2:raise OSError('injected write failure')
        original_write(root,path,value)
    cpu_control.write=interrupted
    assert cpu_control.apply({'op':'scene','scene':'desktop'},root,lease)['error']=='write_failed'
    cpu_control.write=original_write
    assert (root/cpu/'scaling_max_freq').read_text().strip()=='1008000'
print('DEVICE_LEASE_CHECK PASS: root-only CPU policy, battery scenes, AC manual gate and restore; host fixtures only')
