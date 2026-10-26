
'use strict';
const definitions={
 backend:{label:'Backend',config:'system',note:'API und Datenbankzugriff. Verbindungen werden vom Backend aus geprüft.',data:[]},
 mqtt:{label:'MQTT-Broker',config:'system',note:'Der Status zeigt die tatsächliche MQTT-Verbindung des Backends. Verbindungen anderer Clients sind daraus nicht ableitbar.',data:[]},
 database:{label:'Datenbank',config:'system',note:'Die Verbindung wird durch eine Datenbankabfrage geprüft. Zugangsdaten werden weiterhin über .env verwaltet.',data:[]},
 'uwb-simulator':{label:'UWB / Position',config:'uwb',note:'Aktuell simulierte Positionsdaten. Ein physischer UWB-Adapter ist noch nicht angebunden. Umgebungsvariablen für Breite und Höhe haben Vorrang.',data:['uwb.position']},
 'flight-simulator':{label:'Flight / Telemetrie',config:'system',note:'Aktuell ein Flugsimulator. Die Anzeige bestätigt keine Verbindung zu einem echten Flugcontroller.',data:['flight.attitude','flight.battery','flight.mode']},
 tracking:{label:'Tracking',config:'tracking',note:'Bestätigt und dedupliziert Grid-Erkennungen. Der Dienststatus stammt aus dem Heartbeat.',data:['detection.confirmed']},
 camera:{label:'Kamera',config:'camera',note:'IP-Kamera mit Livevorschau. IP-Adresse oder vollständige RTSP-/HTTP-Stream-URL eingeben und speichern. Die Kamera wird ohne Neustart gewechselt.',data:[]},
 ai:{label:'ArUco-Erkennung',config:'system',note:'ArUco-Bilderkennung vorhanden (DICT_4X4_1000). Anbindung des Livefeeds an die Erkennung und Veröffentlichung der Erkennungen sind noch nicht implementiert; im Standard-Stack nicht gestartet.',data:[]},
 mission:{label:'Mission',config:'mission',note:'Noch kein eigenständiger Missionsdienst. Missionsparameter werden gespeichert; eine automatische Flugsteuerung ist noch nicht implementiert.',data:['mission.status','mission.progress']},
 'grid-mapping':{label:'Grid-Mapping',config:'grid',note:'Projektion ist als Bibliothek vorhanden; noch kein eigenständiger Dienst. Das Dashboard verwendet die gespeicherte Gridkonfiguration sofort. Vorhandene Funde behalten ihre gespeicherte Zellzuordnung.',data:[]}
};
const schema={
 system:[['service_timeout_seconds','Heartbeat-Zeitlimit (s)','number',5,300],['log_level','Protokollierungsstufe','select',['DEBUG','INFO','WARNING','ERROR']]],
 uwb:[['width_m','Simulationsbreite (m)','number',0.01,1000],['height_m','Simulationshöhe (m)','number',0.01,1000],['altitude_m','Simulationshöhe über Boden (m)','number',0.01,100]],
 tracking:[['proximity_m','Abstand für Duplikaterkennung (m)','number',0.01,100]],
 grid:[['origin.x_m','Ursprung X (m)','number'],['origin.y_m','Ursprung Y (m)','number'],['cell_size_m','Zellgröße (m)','number',0.01,100],['rows','Zeilen','integer',1,100],['columns','Spalten','integer',1,100],['axis_convention','Achsenkonvention','text']],
 mission:[['nominal_flight_height_m','Geplante Flughöhe (m)','number',0.01,100],['speed_m_s','Geplante Geschwindigkeit (m/s)','number',0.01,20],['overlap','Überlappung (0 bis < 1)','number',0,0.99],['scan_strategy','Scanstrategie','select',['boustrophedon']]],
 camera:[['stream.rtsp_url','Kamera-IP oder Stream-URL (leer = trennen)','text'],['frame.width','Bildbreite (px)','integer',1,16384],['frame.height','Bildhöhe (px)','integer',1,16384],['intrinsics.fx_px','Brennweite fx (px)','number',0.01],['intrinsics.fy_px','Brennweite fy (px)','number',0.01],['intrinsics.cx_px','Bildzentrum cx (px)','number'],['intrinsics.cy_px','Bildzentrum cy (px)','number'],['mount.x_m','Montage X (m)','number'],['mount.y_m','Montage Y (m)','number'],['mount.z_m','Montage Z (m)','number'],['mount.roll_deg','Roll (°)','number'],['mount.pitch_deg','Pitch (°)','number'],['mount.yaw_deg','Yaw (°)','number']]
};
const $=id=>document.getElementById(id);const escapeText=value=>String(value??'–').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
let data={},latest={},selectedCell=null,active=null,configDraft=null,busy=false;
const stateLabels={online:'Online',offline:'Offline',degraded:'Eingeschränkt',starting:'Startet',error:'Fehler',unknown:'Unbekannt'};
const badge=state=>`<span class="badge ${escapeText(state)}">${stateLabels[state]||'Unbekannt'}</span>`;
const detail=(label,value)=>`<div class="detail"><span class="muted">${escapeText(label)}</span><span>${value}</span></div>`;
function serviceState(id){if(id==='camera')return data.camera?.status||'unknown';if(id==='mqtt'||id==='database')return data.connections ? (data.connections[id]?'online':'offline'):'unknown';return (data.services||[]).find(s=>s.service===id)?.status||'unknown';}
async function request(url,options){const response=await fetch(url,{signal:AbortSignal.timeout(10000),...options});if(!response.ok){let body;try{body=await response.json()}catch{body={detail:response.statusText}}throw Error(`${response.status}: ${typeof body.detail==='string'?body.detail:JSON.stringify(body.detail)}`)}return response.status===204?null:response.json();}
function columnLabel(n){let label='';for(n++;n;n=Math.floor((n-1)/26))label=String.fromCharCode(65+(n-1)%26)+label;return label;}
function renderOverview(){
 const items=data.detections||[],services=data.services||[]; $('count').textContent=data.detections?items.length:'–';$('online-count').textContent=data.services?services.filter(s=>s.status==='online').length:'–';
 const pos=data.position?.position;const fresh=data.position?.timestamp&&Date.now()-Date.parse(data.position.timestamp)<(data.config?.system.service_timeout_seconds||15)*1000;
 $('position').textContent=pos?`${pos.x_m.toFixed(2)} / ${pos.y_m.toFixed(2)} m`:'Keine Daten';
 $('position-note').textContent=pos&&!fresh?'Positionsdaten sind veraltet; die Markierung wird ausgeblendet.':'';
 $('service-summary').innerHTML=Object.entries(definitions).map(([id,def])=>detail(def.label,`<a href="/services/${id}">${badge(serviceState(id))}</a>`)).join('');
 const grid=data.config?.grid;if(grid){$('grid-info').textContent=`${grid.columns} × ${grid.rows} Zellen · ${grid.cell_size_m} m pro Zelle · Ursprung ${grid.origin.x_m} / ${grid.origin.y_m} m`;
 const counts={};items.forEach(d=>counts[d.grid_cell]=(counts[d.grid_cell]||0)+1);
 const col=pos?Math.floor((pos.x_m-grid.origin.x_m)/grid.cell_size_m):-1,row=pos?Math.floor((pos.y_m-grid.origin.y_m)/grid.cell_size_m):-1;
 const out=[];for(let r=grid.rows-1;r>=0;r--)for(let c=0;c<grid.columns;c++){const cell=columnLabel(c)+(r+1),count=counts[cell]||0;out.push(`<button type="button" class="cell ${count?'found':''} ${selectedCell===cell?'selected':''} ${fresh&&col===c&&row===r?'position':''}" data-cell="${cell}" aria-pressed="${selectedCell===cell}">${cell}<small>${count?count+' Funde':'·'}</small></button>`)}
 $('grid').style.gridTemplateColumns=`repeat(${grid.columns}, minmax(46px,1fr))`;$('grid').innerHTML=out.join('');
 if(fresh&&(col<0||row<0||col>=grid.columns||row>=grid.rows))$('position-note').textContent='Die aktuelle Position liegt außerhalb des Grids.';
 }renderDetections();
}
function renderDetections(){const query=$('search').value.toLowerCase();const items=(data.detections||[]).filter(d=>(!selectedCell||d.grid_cell===selectedCell)&&[d.class_name,d.number,d.grid_cell].some(v=>String(v??'').toLowerCase().includes(query)));
 $('filter-label').textContent=selectedCell?`Zelle ${selectedCell}`:'';
 $('detections').innerHTML=items.map(d=>`<tr><td>${escapeText(new Date(d.timestamp).toLocaleString('de-DE'))}</td><td>${escapeText(d.class_name)}</td><td>${escapeText(d.number)}</td><td>${escapeText(d.grid_cell)}</td><td>${(d.confidence*100).toFixed(1)} %</td><td>${Number(d.world.x_m).toFixed(2)} / ${Number(d.world.y_m).toFixed(2)} m</td><td><button class="secondary" data-detection="${escapeText(d.id)}">Ansehen</button></td></tr>`).join('')||`<tr><td colspan="7">${data.detections?'Keine passenden Funde vorhanden.':'Datenbankeinträge konnten noch nicht geladen werden.'}</td></tr>`;
}
function renderService(){if(!active)return;const def=definitions[active];const status=(data.services||[]).find(s=>s.service===active);let html=detail('Dienststatus',badge(serviceState(active)));
 html+=detail('Letzter Heartbeat',status?escapeText(new Date(status.timestamp).toLocaleString('de-DE')):'Noch keiner empfangen');
 if(status)html+=detail('Version',escapeText(status.version));
 html+=detail('Backend → MQTT',badge(serviceState('mqtt')))+detail('Backend → Datenbank',badge(serviceState('database')));
 const sources=def.data.map(key=>[key,latest[key]||data.telemetry?.[key]||(key==='uwb.position'?data.position:null)]).filter(([,value])=>value&&Object.keys(value).length);
 if(active==='camera')html+=detail('Kameraverbindung',escapeText(data.camera?.message||'Wird geprüft …'));$('service-status').innerHTML=html;$('service-note').textContent=def.note;$('service-data').textContent=sources.length?JSON.stringify(Object.fromEntries(sources),null,2):'Keine Daten für diese Komponente empfangen. Ein Heartbeat allein bestätigt keine Hardwareverbindung.';
 if(!configDraft&&data.config)buildForm();
}
function buildForm(){const def=definitions[active];configDraft=structuredClone(data.config[def.config]);$('settings-note').textContent=def.config==='system'?'Gemeinsame Systemeinstellungen für alle Dienste. Das Heartbeat-Zeitlimit gilt sofort; die Protokollierungsstufe nach einem Neustart. Verbindungsadressen werden über .env / Docker Compose verwaltet.':(def.config==='camera'?'Kamera-Adresse speichern, um sofort zu verbinden. Eine reine IP wird als rtsp://IP verwendet. Viele Kameras benötigen zusätzlich einen Stream-Pfad, Port und Zugangsdaten. Kalibrierung gilt nur für die jeweilige Kamera; GStreamer wird nicht verwendet.':def.config==='grid'?'Änderungen gelten sofort für die Gridanzeige.':'Änderungen gelten nach einem Neustart des Dienstes.');
 $('fields').innerHTML=schema[def.config].map(([path,label,type,min,max])=>{const value=path.split('.').reduce((v,key)=>v[key],configDraft);let input;if(type==='select')input=`<select name="${path}">${min.map(v=>`<option ${value===v?'selected':''}>${v}</option>`).join('')}</select>`;else input=`<input name="${path}" type="${type==='text'?'text':'number'}" value="${escapeText(value??'')}" ${type!=='text'?`step="${type==='integer'?'1':'any'}" ${min!==undefined?`min="${min}"`:''} ${max!==undefined?`max="${max}"`:''} required`:'maxlength="4000"'}>`;return `<label>${label}${input}</label>`}).join('');$('save').disabled=false;
}
function navigate(){const id=location.pathname.split('/')[2];active=definitions[id]?id:null;configDraft=null;$('save-result').textContent='';$('fields').innerHTML='';$('save').disabled=true;$('overview').hidden=!!active;$('service-page').hidden=!active;$('title').textContent=active?definitions[active].label:'Übersicht';$('subtitle').textContent=active?'Dienststatus, Verbindungen und Konfiguration':'Grid, Position und bestätigte Funde';document.title=`Grideye · ${$('title').textContent}`;document.querySelectorAll('nav a').forEach(a=>a.setAttribute('aria-current',a.pathname===location.pathname?'page':'false'));$('camera-preview').hidden=active!=='camera';if(active)renderService();else renderOverview();}
async function refresh(){if(busy)return;busy=true;const endpoints={camera:'/api/v1/camera/status',health:'/api/v1/system/health',services:'/api/v1/system/services',connections:'/api/v1/system/connections',position:'/api/v1/drone/position',telemetry:'/api/v1/drone/telemetry',detections:'/api/v1/detections',config:'/api/v1/config',simulation:'/api/v1/simulation',missions:'/api/v1/missions'};const failures=[];await Promise.all(Object.entries(endpoints).map(async([key,url])=>{try{data[key]=await request(url)}catch(error){delete data[key];failures.push(`${key}: ${error.message}`)}}));$('errors').textContent=failures.length?'Daten konnten nicht geladen werden: '+failures.join('\n'):'';$('api-state').textContent=data.health?'API erreichbar':'API nicht erreichbar';$('api-state').className='badge '+(data.health?'online':'offline');$('updated').textContent='Aktualisiert: '+new Date().toLocaleTimeString('de-DE');renderOverview();renderService();busy=false;}
$('nav').innerHTML='<a href="/">Übersicht</a><div class="nav-label">SERVICES</div>'+Object.entries(definitions).map(([id,def])=>`<a href="/services/${id}">${def.label}</a>`).join('');
$('nav').addEventListener('click',event=>{const link=event.target.closest('a');if(link&&!event.ctrlKey&&!event.metaKey){event.preventDefault();history.pushState({},'',link.href);navigate()}});window.addEventListener('popstate',navigate);
$('grid').addEventListener('click',event=>{const cell=event.target.closest('[data-cell]');if(cell){selectedCell=selectedCell===cell.dataset.cell?null:cell.dataset.cell;renderOverview()}});$('search').addEventListener('input',renderDetections);$('clear-filter').onclick=()=>{selectedCell=null;renderOverview()};
$('detections').addEventListener('click',event=>{const button=event.target.closest('[data-detection]');if(button){const item=data.detections.find(d=>d.id===button.dataset.detection);$('detection-detail').hidden=false;$('detection-json').textContent=JSON.stringify(item,null,2)}});
$('settings-form').addEventListener('submit',async event=>{event.preventDefault();if(!configDraft)return;const name=definitions[active].config,submittedPage=active,payload=structuredClone(configDraft);for(const [path,,type] of schema[name]){const parts=path.split('.'),key=parts.pop();let target=payload;for(const part of parts)target=target[part];const value=event.target.elements.namedItem(path).value;target[key]=type==='number'||type==='integer'?Number(value):value||null;} $('save').disabled=true;$('save-result').textContent='Wird gespeichert …';try{const result=await request('/api/v1/config/'+name,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});if(active===submittedPage){configDraft=result.config;$('save-result').textContent=result.restart_required?'Gespeichert. Neustart für Dienstparameter / Protokollierungsstufe erforderlich. Das Heartbeat-Zeitlimit gilt sofort.':(name==='camera'?'Gespeichert. Die neue Kamera wird verbunden; eine leere Adresse trennt die Verbindung.':'Gespeichert. Konfiguration wird angewendet.');}await refresh()}catch(error){if(active===submittedPage)$('save-result').textContent='Speichern fehlgeschlagen: '+error.message}finally{if(active===submittedPage)$('save').disabled=false}});
function connectLive(){const socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws/live`);socket.onmessage=event=>{try{const envelope=JSON.parse(event.data);latest[envelope.type]=envelope.data;if(envelope.type==='simulation.telemetry'&&typeof telemetry==='function')telemetry(envelope.data);if(active)renderService()}catch{}};socket.onclose=()=>setTimeout(connectLive,5000);socket.onerror=()=>socket.close();}
navigate();refresh();setInterval(refresh,3000);connectLive();

let cameraObjectUrl=null,cameraGeneration=0;
async function previewCamera(){
 if(active!=='camera'){
  $('camera-image').hidden=true;
  if(cameraObjectUrl){URL.revokeObjectURL(cameraObjectUrl);cameraObjectUrl=null;}
  setTimeout(previewCamera,500);return;
 }
 const generation=cameraGeneration;
 try{
  const response=await fetch('/api/v1/camera/frame.jpg',{cache:'no-store',signal:AbortSignal.timeout(5000)});
  if(!response.ok)throw Error('Kein aktuelles Livebild. Verbindung wird automatisch erneut versucht.');
  const blob=await response.blob();
  if(active==='camera'&&generation===cameraGeneration){
   const previous=cameraObjectUrl;cameraObjectUrl=URL.createObjectURL(blob);
   $('camera-image').src=cameraObjectUrl;$('camera-image').hidden=false;
   $('camera-message').textContent='Livebild';if(previous)URL.revokeObjectURL(previous);
  }
 }catch(error){if(generation===cameraGeneration){$('camera-image').hidden=true;$('camera-message').textContent=data.camera?.configured===false?'Keine Kamera konfiguriert. Unter Einstellungen eine Adresse eingeben und speichern.':error.message;}}
 setTimeout(previewCamera,200);
}
$('settings-form').addEventListener('submit',()=>{if(active==='camera'){cameraGeneration++;$('camera-image').hidden=true;$('camera-message').textContent='Kameraverbindung wird aktualisiert …';}});
previewCamera();
