const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os');
(async()=>{
 const output=fs.mkdtempSync(path.join(os.tmpdir(),'clip-test-'));
 const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{})});
 try{
  const page=await browser.newPage({viewport:{width:1400,height:1100},acceptDownloads:true});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
  // Test seam supplies synthetic screen frames; real MediaRecorder and all app code run.
  await page.addInitScript(()=>{
   navigator.mediaDevices.getDisplayMedia=async()=>{
    const canvas=document.createElement('canvas');canvas.width=640;canvas.height=360;
    const ctx=canvas.getContext('2d');let frame=0;
    const draw=()=>{ctx.fillStyle='#24585b';ctx.fillRect(0,0,640,360);ctx.fillStyle='white';ctx.font='30px sans-serif';ctx.fillText('Synthetic screen '+frame++,50,180);};draw();
    const timer=setInterval(draw,100);const stream=canvas.captureStream(10);
    stream.getVideoTracks()[0].addEventListener('ended',()=>clearInterval(timer));return stream;
   };
  });
  const base=process.env.TEST_URL||'http://127.0.0.1:5120';await page.goto(base);
  await page.getByRole('button',{name:'Choose screen & record'}).click();
  await page.waitForTimeout(1500);
  await page.getByRole('button',{name:'Stop recording',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Recording ready'));
  await page.locator('#preview').evaluate(v=>v.play());
  await page.waitForFunction(()=>document.querySelector('#preview').currentTime>0);
  const download=page.waitForEvent('download');await page.getByRole('link',{name:'Download recording',exact:true}).click();
  const file=path.join(output,'recording.webm');await(await download).saveAs(file);assert.ok(fs.statSync(file).size>100);
  await page.getByLabel('Recording title').fill('A synthetic walkthrough');
  await page.getByRole('button',{name:'Upload & create link'}).click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('owner key'));
  await page.getByLabel('Owner key',{exact:true}).fill(process.env.OWNER_TOKEN||'test-'+'a'.repeat(40));
  await page.getByRole('button',{name:'Upload & create link'}).click();
  await page.locator('#sharelink').waitFor({state:'visible'});
  const url=await page.locator('#sharelink').getAttribute('href');
  const viewer=await browser.newPage();await viewer.goto(url);
  assert.equal(await viewer.locator('h1').innerText(),'A synthetic walkthrough');
  await viewer.locator('video').evaluate(v=>v.play());await viewer.waitForFunction(()=>document.querySelector('video').currentTime>0);
  await page.screenshot({path:path.join(__dirname,'artifacts/studio.png'),fullPage:true});
  await viewer.screenshot({path:path.join(__dirname,'artifacts/viewer.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(__dirname,'artifacts/mobile.png'),fullPage:true});
  await page.getByRole('button',{name:'Revoke & delete',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#library-status').textContent.includes('No shared'));
  assert.equal((await viewer.goto(url)).status(),404);
  await page.getByRole('button',{name:'Forget key',exact:true}).click();assert.equal(await page.locator('#key').inputValue(),'');
  await page.locator('#file').setInputFiles(file);await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('File opened'));
  await page.evaluate(()=>{navigator.mediaDevices.getDisplayMedia=async()=>{throw new DOMException('denied','NotAllowedError');};});
  await page.getByRole('button',{name:'Choose screen & record'}).click();await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('declined'));
  assert.equal(await page.getByRole('button',{name:'Choose screen & record'}).isEnabled(),true);
  assert.deepEqual(errors,[]);
  console.log('PASS synthetic screen → real MediaRecorder → playback → download → upload → public playback → revoke; import, missing key and denied picker recovery. Real picker/microphone remain unverified.');
 }finally{await browser.close();fs.rmSync(output,{recursive:true,force:true});}
})();
