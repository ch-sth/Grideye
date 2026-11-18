'use strict';
let modelOperationBusy=false;
function renderModels(){
 const state=data.modelState;
 if(!state){$('model-current').textContent='Modellverwaltung wird geladen …';return;}
 const selected=state.active_id==='aruco'?'ArUco (DICT_4X4_1000)':state.models.find(model=>model.id===state.active_id)?.name||'Unbekannt';
 $('model-current').textContent=`Aktiv: ${selected}${state.error?' · '+state.error:''}`;
 const entries=[{id:'aruco',name:'ArUco',builtin:true},...state.models];
 $('model-list').innerHTML=entries.map(model=>`<div class="detail"><div><strong>${escapeText(model.name)}</strong><div class="muted">${model.builtin?'Integriert · benötigt keine Modelldatei':`${(model.size_bytes/1024/1024).toFixed(1)} MiB · ${Object.keys(model.classes).length} Klassen · ${escapeText(new Date(model.imported_at).toLocaleString('de-DE'))}`}</div></div><div>${model.id===state.active_id?'<span class="badge online">Aktiv</span>':`<button type="button" class="secondary" data-model-action data-activate-model="${escapeText(model.id)}" ${modelOperationBusy?'disabled':''}>Aktivieren</button>`}</div></div>`).join('');
 const inference=data.aiResult;
 $('model-inference-status').textContent=inference?.message||'Warte auf Kamerabild.';
 $('model-inference-result').textContent=inference?.detections?.length?JSON.stringify(inference.detections.map(item=>({klasse:item.class_name,nummer:item.number,konfidenz:item.class_confidence,bildbereich:item.bbox_px})),null,2):'Keine Erkennungen.';
}
async function changeModel(url,options){
 if(modelOperationBusy)return;
 modelOperationBusy=true;
 document.querySelectorAll('[data-model-action]').forEach(button=>button.disabled=true);
 $('model-operation').textContent='Modell wird übertragen und geprüft. Das bisherige Modell bleibt bis zur erfolgreichen Aktivierung in Betrieb …';
 try{
  const result=await request(url,{...options,signal:AbortSignal.timeout(600000)});
  data.modelState=result;data.aiResult=null;
  const name=result.active_id==='aruco'?'ArUco':result.models.find(item=>item.id===result.active_id)?.name;
  $('model-operation').textContent=`Erfolgreich. ${name} ist jetzt aktiv und gespeichert.`;
  $('model-file').value='';
 }catch(error){
  $('model-operation').textContent='Vorgang fehlgeschlagen: '+error.message;
 }finally{
  modelOperationBusy=false;
  document.querySelectorAll('[data-model-action]').forEach(button=>button.disabled=false);
  renderModels();
 }
}
$('model-path-form').addEventListener('submit',event=>{
 event.preventDefault();
 changeModel('/api/v1/ai/models/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:$('model-path').value.trim()})});
});
$('model-upload-form').addEventListener('submit',event=>{
 event.preventDefault();const file=$('model-file').files[0];if(!file)return;
 if(!file.name.toLowerCase().endsWith('.pt')){$('model-operation').textContent='Bitte eine .pt-Datei auswählen.';return;}
 if(file.size>512*1024*1024){$('model-operation').textContent='Die Datei ist größer als 512 MiB.';return;}
 changeModel('/api/v1/ai/models/upload?filename='+encodeURIComponent(file.name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});
});
$('model-list').addEventListener('click',event=>{
 const button=event.target.closest('[data-activate-model]');if(!button)return;
 changeModel('/api/v1/ai/models/activate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model_id:button.dataset.activateModel})});
});
if(active==='models')renderModels();
