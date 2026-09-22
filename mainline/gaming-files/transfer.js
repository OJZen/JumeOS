'use strict';
const $ = id => document.getElementById(id);
let folder = '', offset = 0, next = null, generation = 0, busy = false, xhr = null, cancelled = false, writable = false;
const units = n => n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KiB` : n < 1073741824 ? `${(n / 1048576).toFixed(1)} MiB` : `${(n / 1073741824).toFixed(2)} GiB`;
const message = text => { $('message').textContent = text; };
function disconnected(text) { $('connection').textContent = '连接已断开'; $('connection').classList.remove('ready'); writable = false; $('files').disabled = true; $('dropzone').classList.add('unavailable'); message(text); }
async function api(path, options = {}) {
  let response;
  try { response = await fetch(path, {credentials: 'same-origin', cache: 'no-store', ...options}); }
  catch { disconnected('无法连接掌机，请检查 Wi-Fi 或重新开启共享。'); throw Error('网络连接已中断'); }
  const body = await response.json();
  if (!response.ok) {
    if (response.status === 401) { $('pairing').hidden = false; $('workspace').hidden = true; }
    throw Error(body.error || '请求失败');
  }
  return body;
}
async function pair(code) {
  try {
    await api('/api/session', {method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({code})});
    $('code').value = ''; message(''); await load();
  } catch (error) { message(error.message); }
}
function crumb(label, destination) {
  const button = document.createElement('button'); button.type = 'button'; button.textContent = label;
  button.addEventListener('click', () => { folder = destination; offset = 0; load().catch(error => message(error.message)); });
  $('breadcrumbs').append(button);
}
async function load() {
  const current = ++generation, path = folder;
  const data = await api('/api/list?' + new URLSearchParams({path, offset}));
  if (current !== generation) return;
  $('pairing').hidden = true; $('workspace').hidden = false; $('connection').textContent = '已连接掌机'; $('connection').classList.add('ready');
  $('rootName').textContent = data.rootName; writable = data.writable; $('files').disabled = !writable || busy;
  $('limits').textContent = `${writable ? '可上传' : '此目录只读'} · 剩余 ${units(data.free)} · 单文件上限 ${units(data.maxFile)} · 每批最多 64 个文件`;
  $('dropzone').classList.toggle('unavailable', !writable || busy);
  $('breadcrumbs').replaceChildren(); crumb('共享根目录', '');
  const parts = path ? path.split('/') : []; parts.forEach((part, i) => crumb(part, parts.slice(0, i + 1).join('/')));
  $('entries').replaceChildren();
  const collator = new Intl.Collator(undefined, {numeric:true, sensitivity:'base'});
  data.files.sort((a,b) => Number(b.directory) - Number(a.directory) || collator.compare(a.name,b.name));
  for (const file of data.files) {
    const fullPath = path ? path + '/' + file.name : file.name;
    const row = document.createElement('div'); row.className = 'entry'; row.setAttribute('role','listitem');
    const icon = document.createElement('span'); icon.className = 'kind'; icon.textContent = file.directory ? '▱' : '▤'; icon.setAttribute('aria-hidden','true');
    const name = document.createElement('div'); name.className = 'fileName';
    const title = document.createElement('strong'); title.textContent = file.name;
    const detail = document.createElement('p'); detail.textContent = (file.directory ? '文件夹' : units(file.size)) + ' · ' + new Date(file.modified * 1000).toLocaleString(); name.append(title,detail);
    let action;
    if (file.directory) { action = document.createElement('button'); action.textContent = '打开'; action.addEventListener('click', () => {folder = fullPath; offset = 0; load().catch(error => message(error.message));}); }
    else { action = document.createElement('a'); action.className = 'button'; action.textContent = '下载'; action.href = '/api/download?' + new URLSearchParams({path:fullPath}); action.download = file.name; }
    action.setAttribute('aria-label',(file.directory ? '打开 ' : '下载 ') + file.name); row.append(icon,name,action); $('entries').append(row);
  }
  if (!data.files.length) { const empty = document.createElement('p'); empty.textContent = '此目录还没有文件。'; $('entries').append(empty); }
  next = data.next; $('previous').disabled = offset === 0; $('next').disabled = next === null;
  $('pageInfo').textContent = `第 ${Math.floor(offset / 200) + 1} 页` + (data.limited ? ' · 目录过大，请在掌机上整理子目录' : '');
}
function uploadOne(file, destination, position, count) {
  return new Promise((resolve,reject) => {
    xhr = new XMLHttpRequest(); xhr.open('PUT','/api/upload?' + new URLSearchParams({path:destination, name:file.name})); xhr.timeout = 7200000;
    $('taskTitle').textContent = `${position}/${count} · ${file.name}`; $('progress').value = 0;
    xhr.upload.onprogress = event => { $('progress').value = event.lengthComputable ? event.loaded * 100 / event.total : 0; $('taskStatus').textContent = `发送到 /${destination} · ${units(event.loaded)} / ${units(file.size)}${event.loaded === event.total ? ' · 等待掌机保存…' : ''}`; };
    xhr.onload = () => { let data; try {data = JSON.parse(xhr.responseText);} catch {data = {error:'服务器返回无效响应'};} if (xhr.status === 201) {$('progress').value = 100; $('taskStatus').textContent = '掌机已保存此文件'; resolve();} else reject(Error(data.error || '上传失败')); };
    xhr.onerror = () => reject(Error('网络中断；未完成文件不会作为正式文件出现'));
    xhr.ontimeout = () => reject(Error('上传超时，请重新连接'));
    xhr.onabort = () => reject(Error('已取消队列；已完成的文件会保留'));
    xhr.send(file);
  });
}
async function upload(files) {
  if (busy || !writable) return;
  const queue = Array.from(files), destination = folder;
  if (!queue.length) return;
  if (queue.length > 64 || queue.some(file => file.size > 8 * 1024**3)) {message('每批最多 64 个文件，单文件最多 8 GiB。'); return;}
  busy = true; cancelled = false; $('task').hidden = false; $('files').disabled = true; $('cancel').disabled = false; message('');
  $('dropzone').classList.add('unavailable');
  let completed = 0;
  try { for (const file of queue) {if (cancelled) break; await uploadOne(file,destination,completed + 1,queue.length); completed++;} message(`已上传 ${completed} 个文件。`); }
  catch (error) {message(`${error.message}。已完成 ${completed} 个文件；未自动重试。`);}
  finally {busy = false; xhr = null; $('files').value = ''; $('files').disabled = !writable; $('cancel').disabled = true; try {await load();} catch(error) {message(error.message);} }
}
$('pairForm').addEventListener('submit', event => {event.preventDefault(); pair($('code').value);});
$('files').addEventListener('change', event => upload(event.target.files));
$('cancel').addEventListener('click', () => {cancelled = true; if(xhr) xhr.abort();});
$('refresh').addEventListener('click', () => load().catch(error => message(error.message)));
$('previous').addEventListener('click', () => {offset = Math.max(0,offset - 200); load().catch(error => message(error.message));});
$('next').addEventListener('click', () => {if(next !== null){offset = next; load().catch(error => message(error.message));}});
for (const type of ['dragenter','dragover']) $('dropzone').addEventListener(type, event => {event.preventDefault(); if(!busy && writable) $('dropzone').classList.add('drag');});
for (const type of ['dragleave','drop']) $('dropzone').addEventListener(type, event => {
  event.preventDefault(); $('dropzone').classList.remove('drag');
  if(type === 'drop') {
    if(Array.from(event.dataTransfer.items || []).some(item => item.webkitGetAsEntry?.()?.isDirectory)) {message('暂不直接上传文件夹，请先压缩为 ZIP。'); return;}
    upload(event.dataTransfer.files);
  }
});
window.addEventListener('beforeunload', event => {if(busy){event.preventDefault(); event.returnValue = '';}});
const token = location.hash.slice(1); history.replaceState(null,'',location.pathname);
if (token) pair(token); else load().catch(error => message(error.message));
setInterval(() => {if(!document.hidden && !$('workspace').hidden) api('/api/status').catch(() => {});}, 5000);
