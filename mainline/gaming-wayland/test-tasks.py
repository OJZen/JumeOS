#!/usr/bin/env python3
"""Real Wayland close, local thumbnails and per-task evdev isolation; SDK only."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time

assert Path('/.dockerenv').exists()
spec=importlib.util.spec_from_file_location('routing',Path(__file__).with_name('test-input-router.py'))
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
out=Path('/out/tasks');out.mkdir(exist_ok=True)

def wait(check,message,seconds=8):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        if check():return
        time.sleep(.04)
    raise AssertionError(message)

with tempfile.TemporaryDirectory(prefix='jume-tasks-',dir='/run') as directory:
    work=Path(directory);pad=fixture.Pad();nodes=[];shell=None
    try:
        # Delay only the task-image response in the client. The real compositor
        # and UI keep running, proving page entry does not wait for readback.
        delay=work/'delay.c';library=work/'delay.so'
        delay.write_text('''#define _GNU_SOURCE
#include <dlfcn.h>
#include <sys/socket.h>
#include <string.h>
#include <time.h>
ssize_t recvmsg(int fd, struct msghdr *message, int flags) {
    static ssize_t (*real_recvmsg)(int, struct msghdr *, int);
    if (!real_recvmsg) real_recvmsg = dlsym(RTLD_NEXT, "recvmsg");
    ssize_t size = real_recvmsg(fd, message, flags);
    if (size > 0 && size < 1024 && message->msg_iovlen == 1 &&
        memmem(message->msg_iov[0].iov_base, size, "\\\"width\\\":", 8)) {
        struct timespec delay = {0, 800000000}; nanosleep(&delay, 0);
    }
    return size;
}
''')
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(delay),'-ldl','-o',str(library)],check=True)
        entries=[]
        for name,identity in [('files','builtin.files'),('game','test.game')]:
            wrapper=work/(name+'.sh')
            wrapper.write_text('#!/bin/sh\nexport QT_PLUGIN_PATH=/out/qt-wayland/usr/lib/aarch64-linux-gnu/qt6/plugins\n'
                'export LD_LIBRARY_PATH=/out/qt-wayland/usr/lib/aarch64-linux-gnu\n'
                + ('sleep 2\n' if name=='game' else '') +
                f'export R46H_TEST_CLOSE_GATE={work}/{name}.allow-close\nexec /out/test-client game {work}/{name}.json\n')
            wrapper.chmod(0o700)
            entries.append(dict(id=identity,title=name,program=str(wrapper),arguments=[]))
        manifest=work/'applications.json';manifest.write_text(json.dumps(dict(version=1,applications=entries)))
        handles=fixture.delegated_slots()
        with (out/'shell.log').open('w') as log:
            try:
                shell=subprocess.Popen(['/out/linux-build/r46h-shell','--state-dir',str(work/'settings'),
                    '--control-dir',str(work/'control'),'--applications',str(manifest),'--fullscreen',
                    '--handheld-router','/out/input-router','--input-device',str(pad.path),
                    '--uinput-fd',str(handles[0]),'--quit-after','100'],pass_fds=handles,stdout=log,stderr=subprocess.STDOUT,
                    env=dict(os.environ,LD_PRELOAD=str(library)))
            finally:
                for fd in handles:os.close(fd)
        endpoint=work/'control/control.sock'
        def observe(action=None,capture=False):
            request=dict(version=1,id='tasks',op='observe',screenshot=capture)
            if action:
                old=observe();request.update({k:old[k] for k in ('session','sequence','binary_sha256')});request.update(op='tap',action=action)
            with socket.socket(socket.AF_UNIX) as connection:
                connection.settimeout(4);connection.connect(str(endpoint));connection.sendall(json.dumps(request).encode()+b'\n')
                data=b''
                while block:=connection.recv(65536):data+=block
            result=json.loads(data);assert result['ok'],result
            return result
        def state():return observe()['state']
        def game(name):
            path=work/(name+'.json')
            return json.loads(path.read_text()) if path.exists() else {}
        def combo(button,hold=.08):
            pad.emit((1,fixture.KEYS[8],1),(1,fixture.KEYS[button],1))
            time.sleep(hold)
            pad.emit((1,fixture.KEYS[8],0),(1,fixture.KEYS[button],0))
        wait(lambda:endpoint.exists() or shell.poll() is not None,'launcher startup')
        assert shell.poll() is None,(out/'shell.log').read_text()
        wait(lambda:state()['sharedReady'],'router ready')
        for slot in range(4):nodes.append(fixture.event_node(fixture.routed_devices(slot)[0].name))
        observe('accept');combo(3)
        wait(lambda:state()['tasksVisible'] and state()['sharedReady'],'immediate launch/background')
        # First commit may not have reached the renderer; icon-only is valid,
        # but the compositor must survive and resume that same app instance.
        wait(lambda:'pid' in game('files'),'early background app startup')
        early=game('files')['pid']
        observe('accept');wait(lambda:'buttons' in game('files') and state()['sharedReady'],'first app')
        assert game('files')['pid']==early and state()['externalSession'],'early background lost app'
        first=game('files')['pid'];assert game('files')['guid'][16:18]=='49'
        time.sleep(1.1) # Include the first mapped surface in the policy sample.
        previews=state()['taskPreviewCount']
        began=time.monotonic()
        combo(3);wait(lambda:state()['tasksVisible'] and state()['sharedReady'],'Select Y task page')
        elapsed=time.monotonic()-began
        assert elapsed < .7 and state()['taskPreviewCount']==previews,('task page waited for image',elapsed,state())
        assert observe(capture=True)['capture']['status']=='sensitive_entry'
        observe('accept');wait(lambda:state()['externalSession'] and state()['sharedReady'],'resume during readback')
        time.sleep(.9)
        assert state()['activeApplication']=='builtin.files' and not state()['tasksVisible'],'stale preview changed scene'
        combo(3);wait(lambda:state()['tasksVisible'] and state()['sharedReady'],'task reopen after cancelled image')
        wait(lambda:state()['taskPreviewCount']==1,'deferred thumbnail')
        assert state()['taskCount']==1,state()
        observe('back');observe('right');observe('accept')
        wait(lambda:'buttons' in game('game') and state()['sharedReady'],'second app')
        second=game('game')['pid'];assert game('game')['guid'][16:18]=='4a'
        wait(lambda:state()['telemetry']['game'].get('lastFrameAgeMs',-1)>=0,'late-mapped foreground surface sample')
        pad.emit((1,fixture.KEYS[0],1));time.sleep(.15)
        assert any(game('game')['buttons']) and not any(game('files')['buttons']),'background input leak'
        pad.emit((1,fixture.KEYS[0],0));time.sleep(.08)
        combo(9);wait(lambda:not state()['externalSession'] and state()['sharedReady'],'short Select Start home')
        assert state()['page']==0 and state()['taskCount']==2
        wait(lambda:state()['taskPreviewCount']==2,'second deferred thumbnail')
        assert '\nState:\tT' in Path(f'/proc/{second}/status').read_text(),'background game not paused'
        combo(3);wait(lambda:state()['tasksVisible'],'task reopen')
        observe('accept');wait(lambda:state()['activeApplication']=='builtin.files' and state()['sharedReady'],'resume existing app')
        assert game('files')['pid']==first and state()['taskCount']==2
        combo(2);wait(lambda:(work/'files.allow-close.requests').exists(),'Wayland close was not delivered')
        time.sleep(1.8)
        assert Path(f'/proc/{first}').exists() and state()['externalSession'],'cooperative close escalated after refusal'
        (work/'files.allow-close').touch();combo(2)
        # QProcess reaps the PID before the bounded process-group cleanup timer
        # removes the task. Wait for that lifecycle boundary, not just /proc.
        closed={}
        def close_completed():
            closed.update(state())
            return (not Path(f'/proc/{first}').exists() and closed['sharedReady']
                and not closed['externalSession'] and closed['taskCount']==1)
        try:wait(close_completed,'accepted window close/task cleanup')
        except AssertionError as error:raise AssertionError((str(error),closed)) from error
        assert closed['taskPreviewCount']==1,closed
        combo(3);wait(lambda:state()['tasksVisible'],'remaining tasks')
        observe('accept');wait(lambda:state()['activeApplication']=='test.game' and state()['sharedReady'],'game resume')
        wait(lambda:'\nState:\tT' not in Path(f'/proc/{second}/status').read_text(),'resume SIGCONT')
        assert not any(game('game')['buttons']),'held input replay on resume'
        combo(9,2.2);wait(lambda:state()['taskCount']==0 and state()['sharedReady'],'long Select Start kill')
        assert not Path(f'/proc/{second}').exists()
        assert state()['taskPreviewCount']==0,'ended task retained thumbnail'
        result=dict(status='TASKS_WAYLAND_HOST_PASS',taskPageReadyMs=round(elapsed*1000,1),checks=['two concurrent apps','four isolated pads',
            'immediate launch/background/resume before first-frame guarantee',
            'delayed first surface updates foreground sample',
            'immediate task page during delayed readback','resume cancels stale preview',
            'surface-only local thumbnails/private remote refusal','short-home','game pause/resume',
            'same PID restore','normal close can refuse without TERM','accepted close','long-hold kill','cleanup'],
            boundary='Synthetic evdev/Qt apps on software Weston; no R46H physical acceptance')
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'])
    finally:
        if shell and shell.poll() is None:
            shell.terminate()
            try:shell.wait(timeout=5)
            except subprocess.TimeoutExpired:shell.kill();shell.wait(timeout=3)
        # Abrupt launcher death is owned by the real session cgroup. This fixture
        # has no device supervisor, so clean only its independently verified groups.
        for name in ('files','game'):
            record=work/(name+'.json')
            if not record.exists():continue
            pid=json.loads(record.read_text())['pid']
            proc=Path(f'/proc/{pid}/cmdline')
            if proc.exists() and proc.read_bytes().split(b'\0')[:3]==[b'/out/test-client',b'game',str(record).encode()]:
                assert os.getpgid(pid)==pid
                os.killpg(pid,signal.SIGKILL)
        for node in nodes:node.unlink(missing_ok=True)
        pad.close()
