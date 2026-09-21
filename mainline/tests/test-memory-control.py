#!/usr/bin/env python3
"""Exercise the memory CLI's size/eviction guards without enabling host swap."""
from pathlib import Path
import os,subprocess,tempfile
repo=Path(__file__).resolve().parents[2]
source=(repo/'mainline/gaming-shell/memory-control.sh').read_text()
unit=(repo/'mainline/gaming-shell/r46h-zram.service').read_text()
config=(repo/'mainline/config/r46h.fragment').read_text()
subprocess.run(['/bin/bash','-n',str(repo/'mainline/gaming-shell/memory-control.sh')],check=True)
functions=source[source.index('size_bytes() {'):source.index('owned_file() {')]
mock='''awk() { if [[ $1 == *MemAvailable* ]]; then echo "$AVAILABLE"; else echo "$TOTAL"; fi; }
'''
for size,passed in [('64',True),('512',True),('2048',True),('2049',False),('32',False),('0',False),('0100',False),('1;touch bad',False)]:
 result=subprocess.run(['/bin/bash','-c','set -Eeuo pipefail\n'+mock+functions+'\nsize_bytes "$VALUE"'],env={**os.environ,'TOTAL':'1048576','AVAILABLE':'786432','VALUE':size},capture_output=True,text=True,timeout=5)
 assert (result.returncode==0)==passed,(size,result)
for used,available,passed in [('100000','500000',True),('400000','500000',False),('0','100000',False),('-1','500000',False),('invalid','500000',False)]:
 result=subprocess.run(['/bin/bash','-c','set -Eeuo pipefail\n'+mock+functions+'\ncan_disable "$USED"'],env={**os.environ,'TOTAL':'1048576','AVAILABLE':available,'USED':used},capture_output=True,text=True,timeout=5)
 assert (result.returncode==0)==passed,(used,available,result)
owned=source[source.index('owned_file() {'):source.index('case $1 in')]
with tempfile.TemporaryDirectory(prefix='memory-owned-',dir=repo/'mainline/out/.cache') as tmp:
    state=Path(tmp);target=state/'target';target.write_text('preserve')
    swap=state/'swapfile';swap.symlink_to(target)
    (state/'disk-owner').write_text('fixture-id')
    # The second predicate deliberately matches: the first must still reject a symlink.
    code='set -Eeuo pipefail\nstat() { if [[ $2 == %d:%i:%s ]]; then echo fixture-id; else echo 0:0:600:1; fi; }\n'+owned+'\nowned_file || exit 3\n'
    result=subprocess.run(['/bin/bash','-c',code],env={**os.environ,'state':str(state),'swapfile':str(swap)},capture_output=True,text=True,timeout=5)
    assert result.returncode==3 and target.read_text()=='preserve',result
assert '/etc/fstab' not in source
assert 'zram-generation' in source and 'disk-owner' in source
assert source.count('external-power-required') == 2
assert '6.12.99-r46h-mainline-v0.19-zram-product' in source
assert 'MEMORY_OK zram-already-active' in source and 'zram-policy' in source
assert 'ConditionKernelVersion==6.12.99-r46h-mainline-v0.19-zram-product' in unit
assert 'ExecStart=/usr/local/sbin/r46h-memory-control --zram 256 lz4' in unit
assert 'ExecStop=' not in unit and 'WantedBy=multi-user.target' in unit
for setting in ('CONFIG_SWAP=y', 'CONFIG_ZRAM=m', 'CONFIG_ZRAM_BACKEND_LZ4=y',
                'CONFIG_ZRAM_DEF_COMP_LZ4=y', '# CONFIG_ZRAM_WRITEBACK is not set',
                '# CONFIG_ZSWAP is not set'):
    assert config.count(setting) == 1, setting
print('MEMORY_CONTROL_CHECK PASS: sizes, reserve, ownership and fixed product zram policy; no swapon/swapoff performed')
