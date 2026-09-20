#!/usr/bin/env python3
"""Drive real built-in tool pages through guarded IPC; only disposable save fixtures."""
from pathlib import Path
import argparse,importlib.util,json,os,subprocess,tempfile,time,uuid
repo=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('control',repo/'mainline/gaming-shell/control.py');control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--binary',type=Path,required=True);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--ipc-root',type=Path);args=p.parse_args()
evidence=control.output_directory(args.evidence)
with tempfile.TemporaryDirectory(prefix='tools-check-',dir=repo/'mainline/out/.cache') as temp, tempfile.TemporaryDirectory(prefix='tool.',dir=args.ipc_root or repo/'mainline/.cache') as ipc:
 root=Path(temp);state=root/'state';state.mkdir(mode=0o700);assets=root/'roms';game=assets/'ports/stardewvalley1615'
 for n in ['SVLoader.exe','dlls/StardewPatches.dll','gamedata/Stardew Valley.exe','gamedata/Content/a.xnb','savedata/Saves/farm/save']:
  f=game/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_text('original')
 f=assets/'tools/PortMaster/libs/mono-6.12.0.122-aarch64.squashfs';f.parent.mkdir(parents=True);f.write_text('fixture')
 endpoint=Path(ipc);endpoint.chmod(0o700);sock=endpoint/'control.sock'
 env={**os.environ,'QT_QPA_PLATFORM':'offscreen','QML_DISABLE_DISK_CACHE':'1','QT_DISABLE_SHADER_DISK_CACHE':'1','SDL_NO_SIGNAL_HANDLERS':'1'}
 with (evidence/'runtime.log').open('wb') as log:
  proc=subprocess.Popen([str(args.binary.resolve()),'--state-dir',str(state),'--content-root',str(assets),'--control-dir',str(endpoint),'--test-input-capture','--quit-after','40'],env=env,stdout=log,stderr=subprocess.STDOUT)
  completed=False
  try:
   end=time.monotonic()+15
   while not sock.exists():
    assert proc.poll() is None,'shell exited before IPC';assert time.monotonic()<end,'IPC timeout';time.sleep(.05)
   def ask(op='observe',capture=False,**fields):return control.exchange(sock,dict(version=1,id=str(uuid.uuid4()),op=op,screenshot=capture,**fields))
   current=ask();actions=0
   def tap(name):
    global current,actions
    current=ask('tap',action=name,session=current['session'],sequence=current['sequence'],binary_sha256=current['binary_sha256']);actions+=1;return current['state']
   def wait():
    global current
    deadline=time.monotonic()+15
    while True:
     current=ask()
     if not current['state']['toolBusy']:return current['state']
     assert time.monotonic()<deadline,'tool operation timeout';time.sleep(.1)
   def wait_detail():
    global current
    deadline=time.monotonic()+5
    while True:
     current=ask()
     if current['state']['toolDetailReady']:return current['state']
     assert time.monotonic()<deadline,'tool detail timeout';time.sleep(.02)
   def capture(label):
    response=ask(capture=True);control.save_result(evidence,response);(evidence/(label+'.json')).write_text(json.dumps(response,ensure_ascii=False,indent=2)+'\n')
   def config():return json.loads((state/'tools/settings.json').read_text())['settings']
   assert current['state']['selectedApplication']=='builtin.moonlight'
   tap('favorite');assert 'builtin.moonlight' in json.loads((state/'preview.json').read_text())['applicationFavorites'];tap('favorite')
   tap('right');assert tap('accept')['toolRoute']=='neo';assert not wait()['toolDetailReady']
   tap('accept');tap('back');assert not ask()['state']['toolDetailReady']
   tap('accept');wait_detail();capture('neo');tap('accept');assert not ask()['state']['externalSession']
   tap('down');tap('down');tap('accept');assert config()['neoIntegerScale'] is True
   tap('back');tap('back');assert not ask()['state']['toolOpen']
   tap('right');tap('accept');assert wait()['toolRoute']=='ports';assert not current['state']['toolDetailReady']
   tap('down');tap('up');assert not ask()['state']['toolDetailReady']
   tap('accept');wait_detail();capture('ports');tap('down');tap('down');tap('down');tap('down');tap('accept');wait()
   copied=state/'tools/ports/stardew/saves/Saves/farm/save';assert copied.read_text()=='original';copied.write_text('new progress')
   tap('accept');assert copied.read_text()=='new progress'
   tap('down');tap('down');tap('accept');wait();assert len(list((state/'tools/backups').iterdir()))==1
   assert (game/'savedata/Saves/farm/save').read_text()=='original'
   tap('back');tap('back');tap('nextTab');tap('down');tap('accept');assert wait()['toolRoute']=='usb';wait_detail()
   tap('accept');assert not (state/'tools/usb-profile.json').exists()
   tap('down');tap('accept');assert config()['usbSwapAB'] is True
   tap('down');tap('down');tap('down');assert tap('accept')['choicesOpen']
   tap('nextTab');tap('home');assert ask()['state']['choicesOpen'] and ask()['state']['toolRoute']=='usb'
   tap('down');tap('back');assert config()['usbDeadzone']==10
   tap('accept');tap('down');tap('accept');assert config()['usbDeadzone']==15
   tap('down');tap('accept');wait();export=json.loads((state/'tools/usb-profile.json').read_text());assert export['usbEnabled'] is False and export['reportLength']==14
   settings_file=state/'tools/settings.json';other=root/'must-not-change';other.write_text('keep');settings_file.unlink();settings_file.symlink_to(other)
   for _ in range(4):tap('up')
   tap('accept');assert ask()['state']['toolSaveError'];tap('home');assert ask()['state']['toolRoute']=='usb';assert other.read_text()=='keep'
   settings_file.unlink();tap('back');assert config()['usbSwapAB'] is False;tap('nextTab')
   for _ in range(9):tap('down')
   tap('accept')
   deadline=time.monotonic()+5
   while not ask()['state']['settingsDetailReady']:
    assert time.monotonic()<deadline,'settings detail timeout';time.sleep(.02)
   tap('accept');tap('down');tap('down');tap('accept');assert ask()['state']['fontPercent']==120
   tap('home');tap('nextTab');tap('down');tap('accept');wait();wait_detail();capture('usb-120')
   assert not ask()['state']['toolSaveError']
   tap('back');tap('home');tap('right');tap('accept');wait();tap('accept');wait_detail();capture('neo-120')
   tap('back');tap('back');tap('right');tap('accept');wait();tap('accept');wait_detail();capture('ports-120')
   completed=True
   result={'status':'SHELL_TOOLS_PASS','actions':actions,'checks':['separate routes','stable favorites','save import without overwrite','backup','USB draft/export only','modal isolation','120% font capture'],'boundary':'host fixtures only; no game execution or USB device writes'}
  finally:
   if completed:
    try:proc.wait(timeout=45)
    except subprocess.TimeoutExpired:proc.kill();proc.wait();raise
   if proc.poll() is None:
    proc.terminate()
    try:proc.wait(timeout=5)
    except subprocess.TimeoutExpired:proc.kill();proc.wait()
 assert proc.returncode==0 and not sock.exists(),'normal quit/socket cleanup failed'
 print(json.dumps(result))
 errors=(evidence/'runtime.log').read_text(errors='replace');assert not any(x in errors for x in ['ReferenceError:','TypeError:','Type ToolPage unavailable']),errors[-3000:]
