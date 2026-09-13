#!/usr/bin/env python3
"""Run the page's pure input checks without fabricating browser/streaming input."""
from pathlib import Path
import subprocess
html=Path(__file__).with_name('index.html').read_text()
logic=html.split('<script>',1)[1].split('// UI runtime',1)[0]
subprocess.run(['node','-e',logic+'\nconsole.log("STREAM_INPUT_PAGE_LOGIC_PASS");'],check=True)
assert 'navigator.getGamepads' in html and 'source:\'browser-gamepad-api\'' in html
assert not any(x in html for x in ['https://','http://','new WebSocket','fetch('])
print('LOCAL_ONLY_PAGE_CHECK_PASS; no device or streaming input proof')
# A DOM/canvas fixture checks page state transitions, not rendering or a real gamepad.
script=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const code=fs.readFileSync(process.argv[1],'utf8').split('<script>')[1].split('</script>')[0];
function fixture(initial=[]){
 let pads=initial,next,download,fail=false;
 const context=new Proxy({},{get:()=>()=>{},set:()=>true});
 const element=()=>({textContent:'',value:'',children:[],width:960,height:600,append(x){this.children.push(x)},replaceChildren(){this.children=[]},getContext(){return context},click(){}});
 const nodes=Object.fromEntries(['screen','status','device','pads','reset','export','summary'].map(n=>[n,element()]));
 const sandbox={document:{getElementById:n=>nodes[n],createElement:element},window:{isSecureContext:true},navigator:{getGamepads(){if(fail)throw Error();return pads}},performance:{now:()=>0},requestAnimationFrame:f=>next=f,setTimeout:()=>0,Blob:class{constructor(parts){download=parts[0]}},URL:{createObjectURL:()=>'',revokeObjectURL:()=>{}}};
 vm.runInNewContext(code,sandbox);
 return {nodes,tick:t=>next(t),set:p=>pads=p,deny:()=>fail=true,report(){nodes.export.onclick();return JSON.parse(download)}};
}
const pad=(index,id,x=0,pressed=false)=>({connected:true,index,id,mapping:'standard',axes:[x,0,0,0],buttons:[{value:Number(pressed),pressed}]});
let f=fixture();f.tick(0);assert.equal(f.nodes.status.textContent,'等待真实手柄');
f.set([pad(0,'Sunshine')]);f.tick(16);assert.match(f.nodes.status.textContent,/已连接/);
f.set([pad(0,'Sunshine',1,true)]);f.tick(32);assert.equal(f.report().changes,1);assert.deepEqual(f.report().pressedButtons,[0]);
f.set([]);f.tick(48);assert.equal(f.nodes.status.textContent,'手柄已断开');assert.equal(f.report().connected,false);assert.equal(f.report().gamepad.id,'Sunshine');
f.set([pad(1,'Other')]);f.tick(64);assert.equal(f.report().connected,false);
f.nodes.pads.value='1';f.nodes.pads.onchange();f.tick(80);assert.equal(f.report().gamepad.id,'Other');assert.equal(f.report().changes,0);
f=fixture([pad(0,'One'),pad(1,'Two')]);f.tick(0);assert.match(f.nodes.pads.children[0].textContent,/请选择/);assert.match(f.nodes.status.textContent,/请选择/);
f.deny();f.tick(16);assert.equal(f.nodes.status.textContent,'浏览器未允许手柄访问');
console.log('STREAM_INPUT_PAGE_STATE_PASS: attach, axes/buttons, disconnect, identity, multiple pads, denied API');
'''
subprocess.run(['node','-e',script,str(Path(__file__).with_name('index.html'))],check=True)
