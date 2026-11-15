'use strict';
const $ = id => document.getElementById(id);
let recorder, screen, microphone, chunks=[], blob, objectURL, clock, started=0, busy=false, recording=false, uploading=false;
const MAX_BYTES=100*1024*1024, MAX_SECONDS=300;
function status(text){I18n.text($('status'), text);}
function controls(){
  $('start').disabled=busy||recording||uploading;
  $('stop').disabled=!recording;
  $('file').disabled=busy||recording||uploading;
  $('publish').disabled=busy||recording||uploading||!blob;
  $('microphone').disabled=busy||recording;
}
function release(){
  clearInterval(clock);
  for(const stream of [screen,microphone])stream?.getTracks().forEach(track=>track.stop());
  screen=null;microphone=null;
}
function showRecording(file){
  if(objectURL)URL.revokeObjectURL(objectURL);
  blob=file;objectURL=URL.createObjectURL(file);
  $('preview').src=objectURL;$('preview').hidden=false;$('recorded').hidden=false;
  $('download').href=objectURL;$('download').download=file.type.includes('mp4')?'recording.mp4':'recording.webm';
  $('shared').hidden=true;controls();
}
function stop(){if(recorder&&recorder.state!=='inactive')recorder.stop();}
$('start').onclick=async()=>{
  if(busy||recording||uploading)return;
  if(blob&&!confirm(I18n.t('Start a new recording? Download or share the current one first if you want to keep it.')))return;
  if(!navigator.mediaDevices?.getDisplayMedia||!window.MediaRecorder){status('Screen recording is unavailable. Use a current desktop Chromium browser on localhost or HTTPS.');return;}
  busy=true;controls();
  try{
    screen=await navigator.mediaDevices.getDisplayMedia({video:{frameRate:15},audio:false});
    if($('microphone').checked)microphone=await navigator.mediaDevices.getUserMedia({audio:true,video:false});
    const tracks=[...screen.getVideoTracks(),...(microphone?.getAudioTracks()||[])];
    const mime=['video/webm;codecs=vp9,opus','video/webm;codecs=vp8,opus','video/webm','video/mp4'].find(type=>MediaRecorder.isTypeSupported(type));
    if(!mime)throw Error('This browser cannot create a supported video format.');
    recorder=new MediaRecorder(new MediaStream(tracks),{mimeType:mime,videoBitsPerSecond:2500000});
    chunks=[];let bytes=0;
    recorder.ondataavailable=e=>{if(e.data.size){chunks.push(e.data);bytes+=e.data.size;if(bytes>=MAX_BYTES)stop();}};
    recorder.onerror=()=>{status('Recording encountered a browser error. Check any recovered preview before sharing.');stop();};
    recorder.onstop=()=>{
      recording=false;release();
      const result=new Blob(chunks,{type:recorder.mimeType});chunks=[];
      if(result.size){showRecording(result);status(result.size>MAX_BYTES?'Recording exceeds the sharing limit. Download it locally.':'Recording ready. Preview it, then download or share.');}
      else status('No video was recorded. Try again and keep the chosen screen open.');
      controls();
    };
    screen.getVideoTracks()[0].onended=stop;
    recorder.start(1000);recording=true;started=Date.now();$('timer').textContent='00:00';
    clock=setInterval(()=>{const seconds=Math.floor((Date.now()-started)/1000);$('timer').textContent=`${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;if(seconds>=MAX_SECONDS)stop();},250);
    status('Recording your chosen screen. Use Stop recording or your browser’s Stop sharing control.');
  }catch(e){release();status(e.name==='NotAllowedError'?'Screen or microphone permission was declined. Nothing was uploaded.':e.message);}
  finally{busy=false;controls();}
};
$('stop').onclick=stop;
$('file').onchange=()=>{const file=$('file').files[0];$('file').value='';if(!file)return;if(!['video/webm','video/mp4'].includes(file.type)){status('Choose a WebM or MP4 video.');return;}if(file.size>MAX_BYTES){status('Choose a video smaller than 100 MB.');return;}if(blob&&!confirm(I18n.t('Replace the current recording?')))return;showRecording(file);status('File opened locally. Preview it before sharing.');};
$('preview').onerror=()=>status('The browser cannot play this recording. It may be damaged or use an unsupported codec.');
async function api(path,options={}){
  const token=$('key').value.trim();if(!token)throw Error('Enter your server’s owner key first.');
  const response=await fetch(path,{...options,headers:{...options.headers,Authorization:`Bearer ${token}`}});
  if(!response.ok){const body=await response.json().catch(()=>({error:`Server returned ${response.status}`}));throw Error(body.error);}
  return response.status===204?null:response.json();
}
async function library(){
  try{
    const rows=await api('/api/clips');$('library').replaceChildren();
    I18n.text($('library-status'), rows.length?'{0} shared recordings':'No shared recordings yet.', {0:rows.length});
    for(const row of rows){const li=document.createElement('li'),a=document.createElement('a'),small=document.createElement('small'),button=document.createElement('button');a.href='/v/'+encodeURIComponent(row.id);a.textContent=row.title;a.target='_blank';a.rel='noreferrer';small.textContent=`${(row.size/1024/1024).toFixed(1)} MB · ${new Date(row.created*1000).toLocaleDateString(I18n.locale)}`;I18n.text(button, 'Revoke & delete');button.className='quiet';button.onclick=async()=>{if(!confirm(I18n.t("Delete “{0}” and revoke its link? Downloaded copies cannot be recalled.", {0: row.title})))return;button.disabled=true;try{await api('/api/clips/'+encodeURIComponent(row.id),{method:'DELETE'});if($('sharelink').pathname==='/v/'+row.id)$('shared').hidden=true;await library();}catch(e){I18n.text($('library-status'), e.message);button.disabled=false;}};li.append(a,small,button);$('library').append(li);}
  }catch(e){I18n.text($('library-status'), e.message);}
}
$('connect').onclick=library;
$('forget').onclick=()=>{$('key').value='';$('library').replaceChildren();I18n.text($('library-status'), 'Owner key forgotten.');};
$('publish').onclick=async()=>{
  if(!blob||uploading||recording)return;
  if(blob.size>MAX_BYTES){status('This recording exceeds the 100 MB sharing limit. Download it instead.');return;}
  const title=$('title').value.trim();if(!title){status('Give the recording a title first.');$('title').focus();return;}
  uploading=true;controls();status('Uploading to your server…');
  try{const data=new FormData();data.append('title',title);data.append('file',blob,'recording');const result=await api('/api/clips',{method:'POST',body:data});const link=new URL(result.url,location.origin);$('sharelink').href=link.href;$('sharelink').textContent=link.href;$('shared').hidden=false;status('Shared link created. Anyone with the link can view it.');await library();}
  catch(e){I18n.text($('status'), "Upload not confirmed: {0}. Your local download is still available. Load the library before retrying to check whether the server saved it.", {0:I18n.t(e.message)});}
  finally{uploading=false;controls();}
};
$('copy').onclick=async()=>{try{await navigator.clipboard.writeText($('sharelink').href);status('Share link copied.');}catch{status('Clipboard access was denied. Select and copy the link above.');}};
window.addEventListener('beforeunload',e=>{if(recording||uploading){e.preventDefault();e.returnValue='';}});
controls();
