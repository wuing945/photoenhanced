// Feathered selections in original-photo coordinates. No external requests.
(()=>{
let source=null,image=null,original=null,recent=null,strokes=[],drawing=null,sample=null,scale=1,busy=false,loading=false,hover=null,scheduled=false;
const canvas=$('#editCanvas'),ctx=canvas.getContext('2d'),pick=$('#editSource'),viewport=$('#editViewport');
const status=t=>$('#editorStatus').textContent=t;
function readImage(url){return new Promise((resolve,reject)=>{const im=new Image();im.onload=()=>resolve(im);im.onerror=()=>reject(Error('讀取照片失敗'));im.src=url})}
function requestDraw(){if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;redraw()})}
function redraw(){
  $('#strokeCount').textContent=strokes.length+' 筆編輯';$('#editZoomValue').textContent=Math.round(scale*100)+'%';
  if(!image)return;
  if(canvas.width!==image.naturalWidth||canvas.height!==image.naturalHeight){canvas.width=image.naturalWidth;canvas.height=image.naturalHeight}
  canvas.style.width=Math.round(canvas.width*scale)+'px';canvas.style.height=Math.round(canvas.height*scale)+'px';ctx.clearRect(0,0,canvas.width,canvas.height);ctx.drawImage(image,0,0);
  if($('#showBrush').checked){
    for(let s of [...strokes,...(drawing?[drawing]:[])]){
      ctx.strokeStyle=s.mode==='smooth'?'rgba(65,225,175,.38)':s.mode==='burn'?'rgba(75,130,255,.48)':'rgba(255,135,100,.45)';ctx.fillStyle=ctx.strokeStyle;ctx.lineWidth=s.radius*Math.min(canvas.width,canvas.height)*2;ctx.lineCap='round';ctx.lineJoin='round';ctx.beginPath();s.points.forEach((p,i)=>{const x=p[0]*canvas.width,y=p[1]*canvas.height;i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke();
      if(s.points.length===1){const p=s.points[0];ctx.beginPath();ctx.arc(p[0]*canvas.width,p[1]*canvas.height,ctx.lineWidth/2,0,Math.PI*2);ctx.fill()}
    }
  }
  ctx.lineWidth=1/Math.max(scale,.02);ctx.strokeStyle='rgba(255,255,255,.9)';
  if(sample){const x=sample[0]*canvas.width,y=sample[1]*canvas.height,d=7/scale;ctx.beginPath();ctx.moveTo(x-d,y);ctx.lineTo(x+d,y);ctx.moveTo(x,y-d);ctx.lineTo(x,y+d);ctx.stroke()}
  if(hover&&!busy&&!loading){ctx.beginPath();ctx.arc(hover[0]*canvas.width,hover[1]*canvas.height,+$('#editSize').value,0,Math.PI*2);ctx.stroke()}
}
function fit(){if(!image)return;scale=Math.max(.02,Math.min(1,(viewport.clientWidth-24)/image.naturalWidth,(viewport.clientHeight-24)/image.naturalHeight));$('#editZoom').value=scale;requestDraw()}
function refill(){const chosen=pick.value;pick.replaceChildren(...pending.map(f=>{const o=document.createElement('option');o.value=f.id;o.textContent=f.name;return o}));const j=last.find(j=>j.id===selected);const desired=j?.source_id||chosen;if(pending.some(f=>f.id===desired))pick.value=desired}
async function load(){
  const target=pick.value;source=target;strokes=[];sample=null;drawing=null;recent=null;image=null;original=null;loading=true;$('#editResult').disabled=true;$('#showBrush').checked=true;$('#editSampleInfo').textContent='使用周圍像素修復';ctx.clearRect(0,0,canvas.width,canvas.height);status('讀取來源照片…');
  try{const im=await readImage(base+'/source/'+encodeURIComponent(target));if(source!==target)return;original=im;image=im;fit();status('塗抹要處理的範圍，再按「套用並另存」。切換來源照片會清空筆刷。')}catch(e){status(e.message)}finally{if(source===target)loading=false}
}
$('#editOpen').onclick=()=>{refill();if(!pending.length){notice('請先加入來源照片');return}$('#editor').hidden=false;document.body.style.overflow='hidden';if(source!==pick.value||!image){$('#editSeparation').value=$('#separation_radius').value;$('#editLowRadius').value=$('#low_radius').value;load()}else requestDraw()};
pick.onchange=load;$('#editClose').onclick=()=>{$('#editor').hidden=true;document.body.style.overflow=''};
$('#editUndo').onclick=()=>{if(!busy){strokes.pop();requestDraw();status('已撤銷一筆，按套用重新計算成品。')}};
$('#editClear').onclick=()=>{if(!busy){strokes=[];sample=null;$('#editSampleInfo').textContent='使用周圍像素修復';image=original;requestDraw();status('筆刷已清空；再次套用會從原照重新計算。')}};
$('#editSampleClear').onclick=()=>{sample=null;$('#editSampleInfo').textContent='使用周圍像素修復';requestDraw()};
$('#editFit').onclick=fit;$('#editZoom').oninput=e=>{scale=+e.target.value;requestDraw()};$('#showBrush').onchange=requestDraw;
$('#editOriginal').onclick=()=>{if(original){image=original;requestDraw();status('顯示原照。筆刷尚未套用時，色塊只表示編輯範圍。')}};
$('#editResult').onclick=()=>{if(recent){image=recent;$('#showBrush').checked=false;requestDraw();status('顯示最近一次成品。')}};
$('#editSize').oninput=e=>{$('#editSizeValue').textContent=e.target.value+' px';requestDraw()};$('#editAmount').oninput=e=>$('#editAmountValue').textContent=e.target.value+'%';
function point(e){const r=canvas.getBoundingClientRect();return [Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))]}
canvas.onpointerdown=e=>{
  if(e.button!==0||busy||loading||!image)return;e.preventDefault();
  if(e.altKey){sample=point(e);$('#editSampleInfo').textContent='已取樣紋理（Alt 點選可更換）';requestDraw();return}
  if(strokes.length>=1000){status('已達 1000 筆，請先套用並另存。');return}
  canvas.setPointerCapture(e.pointerId);$('#showBrush').checked=true;
  drawing={mode:$('#editMode').value,radius:+$('#editSize').value/Math.min(canvas.width,canvas.height),amount:+$('#editAmount').value/100,points:[point(e)]};
  if(sample&&['heal','heal_high'].includes(drawing.mode))drawing.sample=sample.slice();requestDraw();
};
canvas.onpointermove=e=>{if(!image)return;hover=point(e);if(drawing){e.preventDefault();const q=drawing.points.at(-1);if(Math.hypot(hover[0]-q[0],hover[1]-q[1])>.0006&&drawing.points.length<10000)drawing.points.push(hover)}requestDraw()};
canvas.onpointerleave=()=>{hover=null;requestDraw()};
canvas.onpointerup=e=>{if(!drawing)return;const p=point(e);if(drawing.points.length<10000)drawing.points.push(p);strokes.push(drawing);drawing=null;requestDraw()};
canvas.onpointercancel=()=>{drawing=null;requestDraw()};
function setBusy(value){busy=value;for(const id of ['editApply','editSource','editUndo','editClear','editAuto','editSeparation','editLowRadius'])$('#'+id).disabled=value;canvas.style.cursor=value?'wait':'crosshair';requestDraw()}
$('#editApply').onclick=async()=>{
  if(busy||loading||!source)return;if(!strokes.length&&!$('#editAuto').checked){status('請先畫出範圍，或勾選自動修圖。');return}
  setBusy(true);const target=source;
  try{
    const s={...settings(),automatic:$('#editAuto').checked,separation_radius:+$('#editSeparation').value,low_radius:+$('#editLowRadius').value};$('#separation_radius').value=s.separation_radius;$('#low_radius').value=s.low_radius;
    const result=await api('start',{ids:[target],settings:s,edits:strokes});selected=result.jobs[0];status('正在套用筆刷並另存原尺寸成品…');
    const waitResult=async()=>{
      try{const d=await api('state'),j=d.jobs.find(j=>j.id===result.jobs[0]);
        if(j&&['done','error','skipped','cancelled'].includes(j.status)){
          if(j.status==='done'){await poll();select(j);recent=await readImage(file(j.output));image=recent;$('#editResult').disabled=false;$('#showBrush').checked=false;requestDraw();status('已另存 '+j.width+' × '+j.height+' 成品。再次套用會從原照重算全部筆刷。')}
          else status(j.message);setBusy(false);
        }else{if(j)status(j.message);setTimeout(waitResult,1200)}
      }catch(e){status('讀取處理進度失敗：'+e.message);setBusy(false)}
    };setTimeout(waitResult,1200);
  }catch(e){status(e.message);setBusy(false)}
};
document.addEventListener('keydown',e=>{if($('#editor').hidden||busy)return;if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'&&!['INPUT','SELECT'].includes(e.target.tagName)){e.preventDefault();$('#editUndo').click()}if(e.key==='Escape')$('#editClose').click()});
})();
