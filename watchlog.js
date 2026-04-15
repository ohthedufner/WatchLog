// ================================================================
// DATA & STATE
// ================================================================
let DB = null;
let serverMode = false;   // true when local Flask server is running

const artistSt = { list:[], filtered:[], sort:'plays', q:'', page:0, per:60, alpha:'All' };
const chanSt   = { list:[], filtered:[], cat:'all', sort:'plays', q:'', page:0, per:60, alpha:'All' };
const songSt   = { list:[], filtered:[], sort:'az',    q:'', qa:'', page:0, per:60, alpha:'All' };

// ================================================================
// ALPHABET FILTER
// ================================================================
const ALPHA_GROUPS = ['All','#','A','B','C','D','E','F','G','H','I','J','K','L','M',
                      'N','O','P','Q','R','S','T','U','V','W','XYZ'];

function alphaKey(name) {
  // Strip any leading non-alpha chars (e.g. "[unknown]" → U, "2-D" → #)
  const raw = (name || '').replace(/^[^a-zA-Z0-9]*/, '');
  const c = raw.charAt(0).toUpperCase();
  if (!c || /[0-9]/.test(c)) return '#';
  if (!'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.includes(c)) return '#';
  if ('XYZ'.includes(c)) return 'XYZ';
  return c;
}

function alphaMatch(name, alpha) {
  if (alpha === 'All') return true;
  return alphaKey(name) === alpha;
}

function buildAlphaBar(barId, st, setFn) {
  const el = document.getElementById(barId);
  if (!el) return;
  el.innerHTML = ALPHA_GROUPS.map(a =>
    `<button class="alpha-btn${st.alpha===a?' active':''}" onclick="${setFn}('${a}')">${a}</button>`
  ).join('');
}

function setArtistAlpha(a) { artistSt.alpha=a; artistSt.page=0; buildAlphaBar('artistAlpha',artistSt,'setArtistAlpha'); applyArtistFilter(); }
function setSongAlpha(a)   { songSt.alpha=a;   songSt.page=0;  buildAlphaBar('songAlpha',  songSt,  'setSongAlpha');   applySongFilter();  }
function setChanAlpha(a)   { chanSt.alpha=a;   chanSt.page=0;  buildAlphaBar('chanAlpha',  chanSt,  'setChanAlpha');   applyChans();       }

let curArtist = null, artVidPage = 0;
let curChan   = null, chanVidPage = 0;
let curSong   = null;
let adminMode = localStorage.getItem('wl_admin_mode') === 'on';

// ================================================================
// PLAYER MODE
// ================================================================
let playerMode = 'embed';   // 'embed' | 'youtube'
const PLAYER_URL = window.location.origin + window.location.pathname.replace(/\/[^/]*$/, '/') + 'player.html';
let playerTab = null;

function setMode(mode) {
  playerMode = mode;
  document.getElementById('modeEmbed').classList.toggle('active',   mode === 'embed');
  document.getElementById('modeYoutube').classList.toggle('active', mode === 'youtube');
}

function sendToPlayer(videoId) {
  if (!videoId) return;
  if (playerMode === 'youtube') {
    window.open('https://www.youtube.com/watch?v=' + videoId, '_blank');
    return;
  }
  // Embed mode: use player.html
  const url = PLAYER_URL + '?v=' + videoId;
  if (!playerTab || playerTab.closed) {
    playerTab = window.open(url, 'watchlog_player');
    setTimeout(() => { if (playerTab) playerTab.postMessage({ videoId }, '*'); }, 1500);
  } else {
    playerTab.focus();
    playerTab.postMessage({ videoId }, '*');
  }
}

function openPageQueue() {
  const pageVids = paginate(curArtist.videos, artVidPage, 20);
  const ids = pageVids.map(v => v.id).filter(Boolean);
  if (!ids.length) return;
  if (playerMode === 'youtube') {
    window.open('https://www.youtube.com/watch?v=' + ids[0], '_blank');
    return;
  }
  const url = PLAYER_URL + '?v=' + ids[0] + '&q=' + ids.join(',');
  if (!playerTab || playerTab.closed) {
    playerTab = window.open(url, 'watchlog_player');
    setTimeout(() => { if (playerTab) playerTab.postMessage({ queue: ids }, '*'); }, 1500);
  } else {
    playerTab.focus();
    playerTab.postMessage({ queue: ids }, '*');
  }
}

// ================================================================
// BOOT
// ================================================================
async function boot() {
  // Detect local editing server
  try {
    const h = await fetch('/api/health', {signal: AbortSignal.timeout(600)});
    if (h.ok) serverMode = true;
  } catch(e) {}

  try {
    const r = await fetch('data.json');
    DB = await r.json();
    document.getElementById('loading').style.display = 'none';
    artistSt.list = (DB.artists || []).slice();
    artistSt.filtered = artistSt.list.slice();
    chanSt.list = (DB.channels || []).slice();
    chanSt.filtered = chanSt.list.slice();
    songSt.list = (DB.songs || []).slice();
    songSt.filtered = songSt.list.slice();
    buildCatTabs();
    buildAlphaBar('artistAlpha', artistSt, 'setArtistAlpha');
    buildAlphaBar('songAlpha',   songSt,   'setSongAlpha');
    buildAlphaBar('chanAlpha',   chanSt,   'setChanAlpha');
    renderHome();
    renderArtistGrid();
    renderChanGrid();
    renderSongGrid();
    handleHash();
  } catch(e) {
    document.getElementById('loading').textContent = 'Error loading data.json — make sure it is in the same folder.';
  }
}

// ================================================================
// ROUTING
// ================================================================
function go(page, param) {
  // Backward compat redirects
  if (page === 'music')  page = 'artists';
  if (page === 'videos') page = 'channels';

  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
  document.getElementById('page-' + page)?.classList.add('active');
  document.querySelector(`.nav-link[data-page="${page}"]`)?.classList.add('active');
  if (page === 'artist')  renderArtistDetail(param);
  if (page === 'channel') renderChanDetail(param);
  if (page === 'song')    renderSongDetail(param);
  window.scrollTo(0, 0);
  const hash = param ? `${page}/${param}` : page;
  if (location.hash.slice(1) !== hash) location.hash = hash;
}

function handleHash() {
  const h = location.hash.slice(1) || 'home';
  if (h.startsWith('artist/'))  { go('artist',  h.slice(7));  return; }
  if (h.startsWith('channel/')) { go('channel', h.slice(8));  return; }
  if (h.startsWith('song/'))    { go('song',    h.slice(5));  return; }
  go(h);
}
window.addEventListener('hashchange', handleHash);

// ================================================================
// UTILS
// ================================================================
function esc(s){ return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') }
function slug(s){ return s.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'') }
function ago(ts){
  if(!ts) return '';
  const d=(new Date()-new Date(ts))/1000;
  if(d<60)        return 'just now';
  if(d<3600)      return Math.floor(d/60)+'m ago';
  if(d<86400)     return Math.floor(d/3600)+'h ago';
  if(d<86400*7)   return Math.floor(d/86400)+'d ago';
  if(d<86400*30)  return Math.floor(d/86400/7)+'w ago';
  if(d<86400*365) return Math.floor(d/86400/30)+'mo ago';
  return Math.floor(d/86400/365)+'y ago';
}
function fmtDur(ms){
  if(!ms) return '';
  const t=Math.round(ms/1000), m=Math.floor(t/60), s=t%60;
  return m+':'+(s<10?'0':'')+s;
}
function badge(cat){
  return `<span class="cat-badge cat-${cat||'unsure'}">${cat||'?'}</span>`;
}
function mtBadge(mt){
  return mt ? `<span class="mt-badge">${esc(mt)}</span>` : '';
}
function thumb(id){ return id ? `https://img.youtube.com/vi/${id}/mqdefault.jpg` : null; }

function videoItem(v, showCat=false){
  const t     = thumb(v.id || v.vid);
  const vid   = v.id || v.vid || '';
  const title = v.t || v.title || '';
  const ch    = v.ch || v.nn || v.rn || '';
  const ts    = v.ts || v.date || '';
  const cat   = v.cat || '';
  const mt    = v.mt || '';
  const msSong= v.ms || '';
  const click = vid ? `onclick="sendToPlayer('${vid}');return false;"` : '';
  return `<a class="video-item" href="#" ${click}>
    <div class="video-thumb">${t
      ? `<img src="${t}" loading="lazy" onerror="this.parentElement.innerHTML='<div class=\\'video-thumb-ph\\'>&#9654;</div>'">`
      : `<div class="video-thumb-ph">&#9654;</div>`}</div>
    <div class="video-info">
      <div class="video-title" title="${esc(title)}">${esc(msSong && msSong!==title ? msSong : title)}</div>
      <div class="video-meta">
        ${ch ? `<span>${esc(ch)}</span>` : ''}
        ${ts ? `<span>${ago(ts)}</span>` : ''}
        ${mt ? mtBadge(mt) : ''}
        ${showCat ? badge(cat) : ''}
      </div>
      ${msSong && msSong!==title ? `<div style="font-family:'Space Mono',monospace;font-size:.54rem;color:var(--text3);margin-top:.1rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(title)}">${esc(title)}</div>` : ''}
    </div>
  </a>`;
}

function paginate(items, page, per){ return items.slice(page*per, (page+1)*per) }

function renderPag(id, total, page, per, fn){
  const tp = Math.ceil(total/per);
  if(tp<=1){ document.getElementById(id).innerHTML=''; return; }
  let h = `<button class="page-btn" onclick="${fn}(${page-1})" ${page===0?'disabled':''}>&#8592;</button>`;
  let s=Math.max(0,page-3), e=Math.min(tp-1,page+3);
  if(s>0) h+=`<button class="page-btn" onclick="${fn}(0)">1</button><span style="color:var(--text3);font-size:.7rem">...</span>`;
  for(let i=s;i<=e;i++) h+=`<button class="page-btn ${i===page?'active':''}" onclick="${fn}(${i})">${i+1}</button>`;
  if(e<tp-1) h+=`<span style="color:var(--text3);font-size:.7rem">...</span><button class="page-btn" onclick="${fn}(${tp-1})">${tp}</button>`;
  h+=`<button class="page-btn" onclick="${fn}(${page+1})" ${page===tp-1?'disabled':''}>&#8594;</button>`;
  h+=`<span class="page-info">${page*per+1}&#8211;${Math.min((page+1)*per,total)} of ${total.toLocaleString()}</span>`;
  document.getElementById(id).innerHTML=h;
}

function mbChips(obj) {
  const chips = [];
  if (obj.mb_country || obj.mb_country) chips.push(obj.mb_country);
  if (obj.mb_type)  chips.push(obj.mb_type);
  if (obj.mb_begin) {
    const yr = obj.mb_begin.slice(0,4);
    const end = obj.mb_end ? obj.mb_end.slice(0,4) : '';
    chips.push(yr + (end ? '–'+end : '–'));
  }
  const tags = (obj.mb_tags || []).slice(0,4);
  tags.forEach(t => chips.push(t));
  if (!chips.length) return '';
  return `<div class="mb-chips">${chips.map(c=>`<span class="mb-chip">${esc(c)}</span>`).join('')}</div>`;
}

// ================================================================
// HOME
// ================================================================
function renderHome(){
  const cc=DB.cat_counts||{}, T=DB.total||0;
  const songs = DB.songs || [];
  document.getElementById('statGrid').innerHTML=`
    <div class="stat-card" onclick="go('channels')"><div class="stat-num">${T.toLocaleString()}</div><div class="stat-label">Total Watches</div></div>
    <div class="stat-card" onclick="go('artists')"><div class="stat-num">${(cc.music||0).toLocaleString()}</div><div class="stat-label">Music Plays</div></div>
    <div class="stat-card" onclick="go('artists')"><div class="stat-num">${(DB.artists||[]).length.toLocaleString()}</div><div class="stat-label">Artists</div></div>
    <div class="stat-card" onclick="go('songs')"><div class="stat-num">${songs.length.toLocaleString()}</div><div class="stat-label">Songs</div></div>
    <div class="stat-card" onclick="go('channels')"><div class="stat-num">${Object.entries(cc).filter(([k])=>k!=='music').reduce((s,[,v])=>s+v,0).toLocaleString()}</div><div class="stat-label">Other</div></div>`;

  document.getElementById('homeRecent').innerHTML = (DB.recent||[]).slice(0,18).map(v=>videoItem(v,true)).join('');

  document.getElementById('homeArtists').innerHTML = (DB.artists||[]).filter(a=>a.name!=='[unknown]').slice(0,12).map(a=>`
    <div onclick="go('artist','${slug(a.name)}')"
      style="display:flex;align-items:center;justify-content:space-between;padding:.45rem 0;border-bottom:1px solid var(--border);cursor:pointer"
      onmouseover="this.style.color='var(--c1)'" onmouseout="this.style.color=''">
      <div>
        <span style="font-size:.8rem;font-weight:500">${esc(a.name)}</span>
        ${a.mb_country ? `<span style="font-family:'Space Mono',monospace;font-size:.55rem;color:var(--c2);margin-left:.4rem">${esc(a.mb_country)}</span>` : ''}
      </div>
      <span style="font-family:'Space Mono',monospace;font-size:.6rem;color:var(--c1)">${(a.plays||0).toLocaleString()}</span>
    </div>`).join('');

  document.getElementById('homeSongs').innerHTML = songs.filter(s=>s.title).slice(0,12).map(s=>`
    <div onclick="go('song','${slug(s.artist)+'/'+slug(s.title)}')"
      style="display:flex;align-items:center;justify-content:space-between;padding:.45rem 0;border-bottom:1px solid var(--border);cursor:pointer"
      onmouseover="this.style.color='var(--c3)'" onmouseout="this.style.color=''">
      <div style="min-width:0;margin-right:.5rem">
        <div style="font-size:.8rem;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(s.title)}</div>
        <div style="font-family:'Space Mono',monospace;font-size:.57rem;color:var(--text2)">${esc(s.artist)}${s.rel_date?` · ${s.rel_date.slice(0,4)}`:''}</div>
      </div>
      <span style="font-family:'Space Mono',monospace;font-size:.6rem;color:var(--c3);flex-shrink:0">${(s.plays||0).toLocaleString()}</span>
    </div>`).join('') || '<div class="empty" style="padding:1rem;font-size:.7rem">No song data yet — run pipeline</div>';
}

// ================================================================
// ARTISTS
// ================================================================
function filterArtists(q){ artistSt.q=q.toLowerCase(); artistSt.page=0; applyArtistFilter(); }
function sortArtists(s)  { artistSt.sort=s; applyArtistFilter(); }
function goArtistPage(p) { artistSt.page=p; renderArtistGrid(); scrollTo(0,0); }

function applyArtistFilter(){
  let list = artistSt.list.filter(a=>a.name!=='[unknown]');
  if(artistSt.q) list=list.filter(a=>a.name.toLowerCase().includes(artistSt.q));
  if(artistSt.alpha!=='All') list=list.filter(a=>alphaMatch(a.name, artistSt.alpha));
  if(artistSt.sort==='az')     list.sort((a,b)=>a.name.localeCompare(b.name));
  else if(artistSt.sort==='recent') list.sort((a,b)=>(b.latest||'').localeCompare(a.latest||''));
  else list.sort((a,b)=>(b.plays||0)-(a.plays||0));
  artistSt.filtered=list; artistSt.page=0; renderArtistGrid();
}

const FEATURED = new Set(['ren','gorillaz','ren-gill']);

function renderArtistGrid(){
  const items = paginate(artistSt.filtered, artistSt.page, artistSt.per);
  if(!items.length){ document.getElementById('artistGrid').innerHTML='<div class="empty">No artists found</div>'; return; }
  document.getElementById('artistGrid').innerHTML = items.map(a=>{
    const s=slug(a.name);
    const feat=FEATURED.has(s);
    const sub=[a.mb_country,a.mb_type].filter(Boolean).join(' · ');
    return `<div class="list-row" onclick="go('artist','${s}')">
      <div class="list-row-name">
        ${feat?'<span class="featured-badge" style="margin-right:.5rem;font-size:.5rem">Featured</span>':''}
        ${esc(a.name)}
      </div>
      ${sub ? `<div class="list-row-sub">${esc(sub)}</div>` : ''}
      <div class="list-row-meta">
        <span>${(a.plays||0).toLocaleString()} plays</span>
        <span style="color:var(--text3)">${ago(a.latest)}</span>
      </div>
    </div>`;
  }).join('');
  renderPag('artistPag', artistSt.filtered.length, artistSt.page, artistSt.per, 'goArtistPage');
}

// ── Artist detail ──────────────────────────────────────────────
const ARTIST_META = {
  'ren': {
    full: 'Ren Gill',
    bio: 'Welsh musician, rapper, poet, and theatrical performer from Brighton. After a decade of undiagnosed Lyme Disease through his late teens and twenties — a period that stripped away his health and momentum — Ren emerged with a body of work unlike almost anyone working today. His music spans rap, folk, spoken word, and large-scale theatrical productions. Hi Ren (2022) is considered by many fans one of the most remarkable performances ever put to video.',
    affiliates: ['The Big Push','The Skinner Brothers','Sam Tompkins','RenMakesStuff'],
    arcs: [
      { name: 'Jenny Arc', desc: 'A series of connected songs telling Jenny\'s story across multiple releases.' },
      { name: "Vincent's Tale", desc: "Continuing narrative across several tracks. Vincent's story unfolds across albums." },
      { name: 'The Seven-Part Series', desc: 'A multi-part video series where Ren reads his own written account of his illness, interspersed with music.' },
      { name: 'Hi Ren', desc: 'A singular theatrical performance — a conversation between two sides of himself.' },
    ]
  },
  'gorillaz': {
    full: 'Gorillaz',
    bio: 'Gorillaz is a fictional band created by musician Damon Albarn (of Blur) and artist Jamie Hewlett. Formed in 1998, the band exists as animated characters — 2-D, Murdoc Niccals, Noodle, and Russel Hobbs — with an ongoing fictional narrative world. Despite (or because of) its fictional nature, Gorillaz has become one of the most artistically serious and commercially successful acts of the 21st century.',
    affiliates: ['Blur','Snoop Dogg','De La Soul','Elton John','Jack Black','Noodle','2-D'],
    arcs: [
      { name: 'Collaborators (50+)', desc: 'An extraordinary roster spanning hip-hop, electronic, world music, rock, and classical.' },
      { name: 'Plastic Beach era', desc: 'The 2010 concept album and its visual world — one of their most ambitious projects.' },
      { name: 'Song Machine series', desc: 'An ongoing episodic release format that began in 2020, releasing songs as "episodes."' },
    ]
  }
};

function renderArtistDetail(s){
  const artist = DB.artists.find(a=>slug(a.name)===s);
  if(!artist){ document.getElementById('artistHero').innerHTML='<div class="empty">Artist not found</div>'; return; }
  curArtist=artist; artVidPage=0;
  const meta = ARTIST_META[s] || null;
  const initials = artist.name.split(/\s+/).map(w=>w[0]||'').join('').slice(0,2).toUpperCase();

  document.getElementById('artistHero').innerHTML=`
    <div class="artist-hero">
      <div class="artist-hero-inner">
        <div class="artist-avatar">${initials}</div>
        <div style="flex:1;min-width:0">
          ${meta ? `<div class="featured-badge">Featured Artist</div>` : ''}
          <div class="artist-hero-name">${esc(meta?.full||artist.name)}</div>
          <div class="artist-hero-stats">
            <span><span class="hl">${(artist.plays||0).toLocaleString()}</span> plays</span>
            <span>Last watched <span class="hl">${ago(artist.latest)}</span></span>
            <span>${artist.videos.length} videos logged</span>
            ${artist.channel_count>1?`<span>${artist.channel_count} channels</span>`:''}
          </div>
          ${artist.mb_id ? `
          <div class="mb-chips" style="margin-top:.6rem">
            ${artist.mb_country ? `<span class="mb-chip">${esc(artist.mb_country)}</span>` : ''}
            ${artist.mb_type    ? `<span class="mb-chip">${esc(artist.mb_type)}</span>` : ''}
            ${artist.mb_begin   ? `<span class="mb-chip">${artist.mb_begin.slice(0,4)}${artist.mb_end?'–'+artist.mb_end.slice(0,4):'–'}</span>` : ''}
            ${(artist.mb_tags||[]).slice(0,5).map(t=>`<span class="mb-chip">${esc(t)}</span>`).join('')}
            ${artist.mb_conf ? `<span class="mb-chip" style="opacity:.6">MB ${artist.mb_conf}%</span>` : ''}
          </div>` : ''}
          ${meta?.bio ? `<div class="artist-notes">${esc(meta.bio)}</div>` : ''}
          ${meta?.affiliates ? `<div style="margin-top:.75rem">
            <div style="font-family:'Space Mono',monospace;font-size:.6rem;color:var(--text3);margin-bottom:.4rem;letter-spacing:.1em">CIRCLE / AFFILIATES</div>
            <div class="affiliates">${meta.affiliates.map(a=>`<span class="affiliate-chip" onclick="searchAffil('${esc(a)}')">${esc(a)}</span>`).join('')}</div>
          </div>` : ''}
        </div>
      </div>
    </div>`;

  let extra = '';
  if(meta?.arcs){
    extra = `<div class="featured-section">
      <div class="featured-section-title">Narrative Arcs &amp; Notable Works</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:.65rem">
        ${meta.arcs.map(arc=>`
          <div style="background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:.85rem">
            <div style="font-weight:600;font-size:.8rem;margin-bottom:.3rem;color:var(--c1)">${esc(arc.name)}</div>
            <div style="font-size:.75rem;color:var(--text2);line-height:1.45">${esc(arc.desc)}</div>
          </div>`).join('')}
      </div>
    </div>`;
  }
  document.getElementById('artistExtra').innerHTML = extra;
  document.getElementById('artistVidCount').textContent = artist.videos.length + ' videos';
  loadSeeAlso(artist.slug || slug(artist.name));
  renderAdminUnknownPanel();
  renderArtistVids();
}

function renderArtistVids(){
  const sorted = (curArtist.videos||[]).slice().sort((a,b)=>(a.t||'').localeCompare(b.t||''));
  const per=20, page=paginate(sorted, artVidPage, per);
  document.getElementById('artistVids').innerHTML = page.map(v=>videoItem(v)).join('');
  renderPag('artistVidPag', sorted.length, artVidPage, per, 'goArtVidPage');
}
function goArtVidPage(p){ artVidPage=p; renderArtistVids(); }

// ================================================================
// ADMIN — UNKNOWN CHANNEL CATEGORIZATION
// ================================================================
const ADMIN_CATS = ['music','news','tech','gaming','comedy','food','tv','other'];

async function renderAdminUnknownPanel() {
  const el = document.getElementById('adminUnknownPanel');
  if (!el) return;
  el.innerHTML = '';
  if (!adminMode || !serverMode) return;
  if (!curArtist || curArtist.slug !== 'unknown') return;

  el.innerHTML = `<div style="padding:.75rem 1.25rem;font-family:'Space Mono',monospace;font-size:.65rem;color:var(--text3)">Loading unsorted channels...</div>`;
  try {
    const r = await fetch('/api/unknown-channels');
    const channels = await r.json();
    if (!channels.length) { el.innerHTML = ''; return; }
    _renderUnknownChannelList(el, channels);
  } catch(e) { el.innerHTML = ''; }
}

function _renderUnknownChannelList(el, channels) {
  const rows = channels.map((ch, i) => `
    <div class="admin-ch-row" id="admin-ch-row-${i}" data-url="${esc(ch.dj_channel_url)}">
      <select class="admin-cat-select" id="admin-cat-${i}">
        <option value="">— pick category —</option>
        ${ADMIN_CATS.map(c=>`<option value="${c}">${c}</option>`).join('')}
      </select>
      <button class="admin-confirm-btn" onclick="confirmChannelCat(${JSON.stringify(ch.dj_channel_url)},${i})">Confirm</button>
      <div class="admin-ch-name" title="${esc(ch.dj_channel_url)}">${esc(ch.dj_name)}</div>
      <div class="admin-ch-plays">${(ch.dj_plays||0).toLocaleString()} plays</div>
    </div>`).join('');

  el.innerHTML = `
    <div class="admin-panel">
      <div class="admin-panel-header">
        <span class="admin-panel-title">Categorize Channels</span>
        <span class="admin-panel-count" id="adminChCount">${channels.length} unsorted</span>
      </div>
      ${rows}
    </div>`;
}

async function confirmChannelCat(url, idx) {
  const sel = document.getElementById('admin-cat-' + idx);
  if (!sel || !sel.value) return;
  const btn = sel.nextElementSibling;
  if (btn) { btn.disabled = true; btn.textContent = '...'; }

  try {
    const r = await fetch('/api/channel-category', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({channel_url: url, category: sel.value}),
    });
    const d = await r.json();
    if (d.ok) {
      const row = document.getElementById('admin-ch-row-' + idx);
      if (row) row.remove();
      const remaining = document.querySelectorAll('[id^="admin-ch-row-"]').length;
      const countEl = document.getElementById('adminChCount');
      if (countEl) countEl.textContent = remaining + ' unsorted';
      if (!remaining) document.getElementById('adminUnknownPanel').innerHTML = '';
    } else {
      if (btn) { btn.disabled = false; btn.textContent = 'Confirm'; }
    }
  } catch(e) {
    if (btn) { btn.disabled = false; btn.textContent = 'Confirm'; }
  }
}

function searchAffil(name){
  document.getElementById('searchInput').value = name;
  onSearch(name);
}

// ================================================================
// SEE ALSO
// ================================================================
let _seeAlsoArtistSlug = '';   // slug of artist currently shown
let _seeAlsoSelected   = null; // {dj_slug, dj_name} chosen in dropdown

async function loadSeeAlso(artistSlug) {
  _seeAlsoArtistSlug = artistSlug;
  _seeAlsoSelected   = null;
  const el = document.getElementById('seeAlsoSection');
  if (!el) return;

  let links = [];
  if (serverMode) {
    try {
      const r = await fetch(`/api/artist-links/${encodeURIComponent(artistSlug)}`);
      links = await r.json();
    } catch(e) {}
  } else {
    // Fall back to data already in the artist object
    const artist = DB.artists.find(a => a.slug === artistSlug);
    links = (artist?.see_also || []).map(s => ({
      wl_al_id:   null,
      wl_to_slug: s.slug,
      dj_name:    s.name,
      wl_label:   s.label || 'See also',
    }));
  }

  renderSeeAlso(el, links);
}

function renderSeeAlso(el, links) {
  const chips = links.map(lk => `
    <span class="see-also-chip" onclick="go('artist','${esc(lk.wl_to_slug)}')">
      ${esc(lk.dj_name)}
      ${serverMode && lk.wl_al_id != null
        ? `<button class="rm" title="Remove" onclick="event.stopPropagation();removeSeeAlso(${lk.wl_al_id})">×</button>`
        : ''}
    </span>`).join('');

  const editUI = serverMode ? `
    <div class="see-also-add">
      <div style="flex:1;position:relative">
        <input class="see-also-input" id="seeAlsoQ" placeholder="Search artists to add..."
          oninput="searchSeeAlso(this.value)" autocomplete="off">
        <div class="see-also-drop" id="seeAlsoDrop"></div>
      </div>
      <label class="see-also-mutual">
        <input type="checkbox" id="seeAlsoMutual" checked style="accent-color:var(--c3)"> Mutual
      </label>
      <button class="see-also-btn" id="seeAlsoAddBtn" onclick="addSeeAlso()" disabled>+ Add</button>
    </div>` : '';

  if (!links.length && !serverMode) { el.innerHTML = ''; return; }

  el.innerHTML = `
    <div class="see-also">
      <div class="see-also-title">See Also</div>
      <div class="see-also-links" id="seeAlsoChips">${chips || '<span style="font-size:.75rem;color:var(--text3)">None yet.</span>'}</div>
      ${editUI}
    </div>`;
}

let _seeAlsoTimer = null;
function searchSeeAlso(q) {
  _seeAlsoSelected = null;
  document.getElementById('seeAlsoAddBtn').disabled = true;
  clearTimeout(_seeAlsoTimer);
  if (!q.trim()) { closeSeeAlsoDrop(); return; }
  _seeAlsoTimer = setTimeout(async () => {
    const r = await fetch(`/api/artists?q=${encodeURIComponent(q)}`);
    const artists = await r.json();
    const drop = document.getElementById('seeAlsoDrop');
    if (!drop) return;
    const filtered = artists.filter(a => a.dj_slug !== _seeAlsoArtistSlug);
    if (!filtered.length) { drop.innerHTML = '<div class="see-also-opt" style="color:var(--text3)">No results</div>'; drop.classList.add('open'); return; }
    drop.innerHTML = filtered.map(a =>
      `<div class="see-also-opt" onclick="selectSeeAlso(${JSON.stringify(a.dj_slug)},${JSON.stringify(a.dj_name)})">
        ${esc(a.dj_name)}<small>${(a.dj_plays||0).toLocaleString()} plays</small>
       </div>`
    ).join('');
    drop.classList.add('open');
  }, 220);
}

function selectSeeAlso(dj_slug, dj_name) {
  _seeAlsoSelected = {dj_slug, dj_name};
  const inp = document.getElementById('seeAlsoQ');
  if (inp) inp.value = dj_name;
  closeSeeAlsoDrop();
  const btn = document.getElementById('seeAlsoAddBtn');
  if (btn) btn.disabled = false;
}

function closeSeeAlsoDrop() {
  const d = document.getElementById('seeAlsoDrop');
  if (d) { d.classList.remove('open'); d.innerHTML = ''; }
}

async function addSeeAlso() {
  if (!_seeAlsoSelected) return;
  const mutual = document.getElementById('seeAlsoMutual')?.checked ?? true;
  const btn    = document.getElementById('seeAlsoAddBtn');
  btn.disabled = true;
  try {
    const r = await fetch('/api/artist-links', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        from_slug: _seeAlsoArtistSlug,
        to_slug:   _seeAlsoSelected.dj_slug,
        mutual,
      }),
    });
    const data = await r.json();
    if (!data.ok && r.status !== 409) { alert(data.error); return; }
  } catch(e) { alert('Server error'); return; }
  const inp = document.getElementById('seeAlsoQ');
  if (inp) inp.value = '';
  _seeAlsoSelected = null;
  await loadSeeAlso(_seeAlsoArtistSlug);   // reload
}

async function removeSeeAlso(linkId) {
  await fetch(`/api/artist-links/${linkId}`, {method: 'DELETE'});
  await loadSeeAlso(_seeAlsoArtistSlug);
}

// Close dropdown when clicking outside
document.addEventListener('click', e => {
  if (!e.target.closest('.see-also-add')) closeSeeAlsoDrop();
});

// ================================================================
// SONGS
// ================================================================
function filterSongs(q)       { songSt.q=q.toLowerCase();  songSt.page=0; applySongFilter(); }
function filterSongArtist(q)  { songSt.qa=q.toLowerCase(); songSt.page=0; applySongFilter(); }
function sortSongs(s)         { songSt.sort=s; applySongFilter(); }
function goSongPage(p)        { songSt.page=p; renderSongGrid(); scrollTo(0,0); }

function applySongFilter(){
  let list = songSt.list.filter(s=>s.title);
  if(songSt.q)  list=list.filter(s=>(s.title||'').toLowerCase().includes(songSt.q));
  if(songSt.qa) list=list.filter(s=>(s.artist||'').toLowerCase().includes(songSt.qa));
  if(songSt.alpha!=='All') list=list.filter(s=>alphaMatch(s.title, songSt.alpha));
  if(songSt.sort==='az')       list.sort((a,b)=>(a.title||'').localeCompare(b.title||''));
  else if(songSt.sort==='artist') list.sort((a,b)=>(a.artist||'').localeCompare(b.artist||'') || (a.title||'').localeCompare(b.title||''));
  else if(songSt.sort==='recent') list.sort((a,b)=>(b.latest||'').localeCompare(a.latest||''));
  else if(songSt.sort==='year')   list.sort((a,b)=>(b.rel_date||'').localeCompare(a.rel_date||''));
  else list.sort((a,b)=>(b.plays||0)-(a.plays||0));
  songSt.filtered=list; songSt.page=0; renderSongGrid();
}

function renderSongGrid(){
  if(!DB.songs||!DB.songs.length){
    document.getElementById('songGrid').innerHTML=`<div class="empty">No song data yet — run the pipeline with watchlog.db to generate song records.</div>`;
    return;
  }
  const items = paginate(songSt.filtered, songSt.page, songSt.per);
  if(!items.length){ document.getElementById('songGrid').innerHTML='<div class="empty">No songs found</div>'; return; }
  document.getElementById('songGrid').innerHTML = items.map(s=>{
    const yr = s.rel_date ? s.rel_date.slice(0,4) : '';
    const key = slug(s.artist)+'/'+slug(s.title);
    return `<div class="list-row" onclick="go('song','${key}')">
      <div class="list-row-name" title="${esc(s.raw_title||s.title)}">${esc(s.title)}</div>
      <div class="list-row-artist">${esc(s.artist)}${s.feat?`<span style="color:var(--text3)"> ft. ${esc(s.feat)}</span>`:''}</div>
      <div class="list-row-meta">
        <span>${(s.plays||0).toLocaleString()} plays</span>
        ${yr ? `<span style="color:var(--text3)">${yr}</span>` : ''}
        ${s.mt ? mtBadge(s.mt) : ''}
      </div>
    </div>`;
  }).join('');
  renderPag('songPag', songSt.filtered.length, songSt.page, songSt.per, 'goSongPage');
}

function findSong(key){
  // key = "artistSlug/titleSlug"
  const [aslug, ...tparts] = key.split('/');
  const tslug = tparts.join('/');
  return (DB.songs||[]).find(s => slug(s.artist)===aslug && slug(s.title)===tslug);
}

function renderSongDetail(key){
  const s = findSong(key);
  if(!s){ document.getElementById('songHero').innerHTML='<div class="empty">Song not found</div>'; return; }
  curSong = s;

  const yr = s.rel_date ? s.rel_date.slice(0,4) : '';
  document.getElementById('songHero').innerHTML=`
    <div class="song-detail-hero">
      <div class="section-label" style="margin-bottom:.35rem">// Song Detail</div>
      <div class="song-detail-title">${esc(s.title)}</div>
      <div style="font-size:.9rem;color:var(--text2);margin-bottom:1rem">
        <span style="cursor:pointer;color:var(--c1)" onclick="go('artist','${esc(s.aslug)}')">${esc(s.artist)}</span>
        ${s.feat ? `<span style="color:var(--text3)"> ft. ${esc(s.feat)}</span>` : ''}
      </div>
      <div class="song-detail-row">
        <div class="song-detail-field">Plays<span>${(s.plays||0).toLocaleString()}</span></div>
        <div class="song-detail-field">Last watched<span>${ago(s.latest)}</span></div>
        ${yr ? `<div class="song-detail-field">Release year<span>${yr}</span></div>` : ''}
        ${s.rel_type ? `<div class="song-detail-field">Release type<span>${esc(s.rel_type)}</span></div>` : ''}
        ${s.rel_title ? `<div class="song-detail-field">Release<span>${esc(s.rel_title)}</span></div>` : ''}
        ${s.dur_ms ? `<div class="song-detail-field">Duration<span>${fmtDur(s.dur_ms)}</span></div>` : ''}
        ${s.mt ? `<div class="song-detail-field">Format<span>${esc(s.mt)}</span></div>` : ''}
      </div>
      ${s.isrc ? `<div class="song-detail-row"><div class="song-detail-field">ISRC<span style="letter-spacing:.05em">${esc(s.isrc)}</span></div></div>` : ''}
      ${s.mb_id ? `
      <div class="mb-chips">
        <span class="mb-chip">MusicBrainz</span>
        <span class="mb-chip" style="font-size:.5rem;opacity:.7">${esc(s.mb_id)}</span>
        ${s.mb_conf ? `<span class="mb-chip" style="opacity:.6">confidence ${s.mb_conf}%</span>` : ''}
      </div>` : ''}
      ${s.raw_title && s.raw_title !== s.title ? `
      <div style="margin-top:.85rem;font-family:'Space Mono',monospace;font-size:.58rem;color:var(--text3)">
        Original title: <span style="color:var(--text2)">${esc(s.raw_title)}</span>
      </div>` : ''}
    </div>`;

  // Source videos
  const vids = s.vids || [];
  document.getElementById('songVidCount').textContent = vids.length + ' video' + (vids.length===1?'':'s');
  document.getElementById('songVids').innerHTML = vids.map(vid => {
    // Find full video info from artist data
    let v = null;
    for(const a of (DB.artists||[])){
      v = a.videos.find(av => av.id === vid);
      if(v){ v = {...v, ch: a.name}; break; }
    }
    return v ? videoItem(v) : `<a class="video-item" href="#" onclick="sendToPlayer('${vid}');return false;">
      <div class="video-thumb"><img src="${thumb(vid)}" loading="lazy" onerror="this.parentElement.innerHTML='<div class=\\'video-thumb-ph\\'>&#9654;</div>'"></div>
      <div class="video-info"><div class="video-title">${vid}</div></div>
    </a>`;
  }).join('') || '<div class="empty" style="padding:1rem">No video IDs recorded</div>';
}

// ================================================================
// CHANNELS (was: VIDEOS)
// ================================================================
const CAT_LABELS = {
  all:'All', tv:'TV', tech:'Tech', food:'Food',
  comedy:'Comedy', news:'News', gaming:'Gaming',
  other:'Other', unsure:'Mystery'
};
const CAT_ORDER = ['all','tv','tech','food','comedy','news','gaming','other','unsure'];

function buildCatTabs(){
  const cc = DB.cat_counts||{};
  document.getElementById('videoCatTabs').innerHTML = CAT_ORDER
    .filter(c => c==='all' || (cc[c]||0)>0)
    .map(c=>`<button class="cat-tab ${c==='all'?'active':''}" data-cat="${c}" onclick="setCat('${c}')">
      ${CAT_LABELS[c]}${c!=='all'?` <span style="opacity:.5;font-size:.55rem">${(cc[c]||0).toLocaleString()}</span>`:''}
    </button>`).join('');
}

function setCat(cat){
  chanSt.cat=cat; chanSt.page=0;
  document.querySelectorAll('.cat-tab').forEach(t=>t.classList.toggle('active', t.dataset.cat===cat));
  applyChans();
}

function filterChans(q){ chanSt.q=q.toLowerCase(); chanSt.page=0; applyChans(); }
function sortChans(s)  { chanSt.sort=s; applyChans(); }
function goChPage(p)    { chanSt.page=p; renderChanGrid(); }
function goChanVidPage(p){ chanVidPage=p; renderChanVids(); }

function applyChans(){
  let list = chanSt.list.slice();
  if(chanSt.cat!=='all') list=list.filter(c=>c.cat===chanSt.cat);
  if(chanSt.q) list=list.filter(c=>c.name.toLowerCase().includes(chanSt.q));
  if(chanSt.alpha!=='All') list=list.filter(c=>alphaMatch(c.name, chanSt.alpha));
  if(chanSt.sort==='az') list.sort((a,b)=>a.name.localeCompare(b.name));
  else list.sort((a,b)=>(b.plays||0)-(a.plays||0));
  chanSt.filtered=list; chanSt.page=0; renderChanGrid();
}

function renderChanGrid(){
  const items=paginate(chanSt.filtered, chanSt.page, chanSt.per);
  const grid = document.getElementById('chanGrid');
  if(!items.length){ grid.innerHTML='<div class="empty">No channels found</div>'; return; }
  let header='';
  if(chanSt.cat==='unsure'){
    header=`<div class="mystery-header">
      <div class="mystery-skull">&#128128;</div>
      <div><div class="mystery-title">Mystery Links</div>
      <div class="mystery-sub">Watch at your own risk. Contents unknown. Proceed with curiosity.</div></div>
    </div>`;
  }
  grid.innerHTML = header + items.map(ch=>{
    const sub=[ch.mb_country,ch.mb_type].filter(Boolean).join(' · ');
    return `<div class="list-row" onclick="go('channel','${slug(ch.name)}')">
      <div class="list-row-name" title="${esc(ch.name)}">${esc(ch.name)}</div>
      ${sub ? `<div class="list-row-sub">${esc(sub)}</div>` : ''}
      <div class="list-row-meta">
        ${ch.cat ? badge(ch.cat) : ''}
        <span>${(ch.plays||0).toLocaleString()} plays</span>
      </div>
    </div>`;
  }).join('');
  renderPag('chanPag', chanSt.filtered.length, chanSt.page, chanSt.per, 'goChPage');
}

function renderChanDetail(s){
  const ch = (DB.channels||[]).find(c=>slug(c.name)===s);
  if(!ch){ document.getElementById('chanHero').innerHTML='<div class="empty">Channel not found</div>'; return; }
  curChan=ch; chanVidPage=0;
  document.getElementById('chanHero').innerHTML=`
    <div class="artist-hero" style="margin-bottom:1.25rem">
      <div class="artist-hero-inner">
        <div class="artist-avatar" style="background:linear-gradient(135deg,var(--c2),var(--c5));font-size:1.3rem">&#128250;</div>
        <div>
          <div class="artist-hero-name">${esc(ch.name)}</div>
          <div class="artist-hero-stats">
            <span><span class="hl" style="color:var(--c2)">${(ch.plays||0).toLocaleString()}</span> plays</span>
            <span>Last watched <span class="hl" style="color:var(--c2)">${ago(ch.latest)}</span></span>
            ${ch.cat ? badge(ch.cat) : ''}
          </div>
          ${(ch.mb_name||ch.mb_country||ch.mb_type) ? `
          <div class="mb-chips">
            ${ch.mb_name    ? `<span class="mb-chip">${esc(ch.mb_name)}</span>` : ''}
            ${ch.mb_country ? `<span class="mb-chip">${esc(ch.mb_country)}</span>` : ''}
            ${ch.mb_type    ? `<span class="mb-chip">${esc(ch.mb_type)}</span>` : ''}
            ${ch.mb_conf    ? `<span class="mb-chip" style="opacity:.6">MB ${ch.mb_conf}%</span>` : ''}
          </div>` : ''}
        </div>
      </div>
    </div>`;
  document.getElementById('chanVidCount').textContent = (ch.videos||[]).length + ' videos';
  renderChanVids();
}

function renderChanVids(){
  const per=20;
  const vids=curChan.videos||[];
  const page=paginate(vids, chanVidPage, per);
  document.getElementById('chanVids').innerHTML = page.map(v=>videoItem(v,true)).join('');
  renderPag('chanVidPag', vids.length, chanVidPage, per, 'goChanVidPage');
}

// ================================================================
// SEARCH
// ================================================================
let _st=null;
function onSearch(q){
  clearTimeout(_st);
  if(!q.trim()){ return; }
  _st=setTimeout(()=>doSearch(q),200);
}

function doSearch(q){
  go('search');
  document.getElementById('searchTitle').textContent=`"${q}"`;
  const ql=q.toLowerCase();
  const artists=(DB.artists||[]).filter(a=>a.name.toLowerCase().includes(ql)&&a.name!=='[unknown]').slice(0,12);
  const songs=(DB.songs||[]).filter(s=>(s.title||'').toLowerCase().includes(ql)||(s.artist||'').toLowerCase().includes(ql)).slice(0,12);
  const chans=(DB.channels||[]).filter(c=>c.name.toLowerCase().includes(ql)).slice(0,12);
  const vids=(DB.recent||[]).filter(v=>(v.t||'').toLowerCase().includes(ql)||(v.ch||'').toLowerCase().includes(ql)).slice(0,24);

  let h='';
  if(artists.length){
    h+=sectionHead('Artists',artists.length);
    h+=`<div class="artist-grid">${artists.map(a=>`<div class="artist-card" onclick="go('artist','${slug(a.name)}')">
      <div class="artist-name">${esc(a.name)}</div>
      <div class="artist-count">${(a.plays||0).toLocaleString()} plays</div>
      ${a.mb_country||a.mb_type?`<div class="artist-mb-line">${[a.mb_country,a.mb_type].filter(Boolean).join(' · ')}</div>`:''}
    </div>`).join('')}</div>`;
  }
  if(songs.length){
    h+=sectionHead('Songs',songs.length);
    h+=`<div class="song-grid">${songs.map(s=>{
      const yr=s.rel_date?s.rel_date.slice(0,4):'';
      const key=slug(s.artist)+'/'+slug(s.title);
      return `<div class="song-card" onclick="go('song','${key}')">
        <div class="song-title">${esc(s.title)}</div>
        <div class="song-artist">${esc(s.artist)}</div>
        <div class="song-meta">${(s.plays||0).toLocaleString()} plays${yr?' · '+yr:''}</div>
        ${s.isrc?`<div class="song-isrc">ISRC ${esc(s.isrc)}</div>`:''}
      </div>`;
    }).join('')}</div>`;
  }
  if(chans.length){
    h+=sectionHead('Channels',chans.length);
    h+=`<div class="channel-grid">${chans.map(c=>`<div class="channel-card" onclick="go('channel','${slug(c.name)}')">
      <div class="channel-name">${esc(c.name)}</div>
      <div class="channel-plays">${(c.plays||0).toLocaleString()} plays</div>
    </div>`).join('')}</div>`;
  }
  if(vids.length){
    h+=sectionHead('Recent Videos',vids.length);
    h+=`<div class="panel"><ul class="video-list">${vids.map(v=>videoItem(v,true)).join('')}</ul></div>`;
  }
  if(!h) h=`<div class="empty">No results for "${esc(q)}"</div>`;
  document.getElementById('searchOut').innerHTML=h;
}

function sectionHead(label, count){
  return `<div style="font-family:'Space Mono',monospace;font-size:.62rem;color:var(--text3);letter-spacing:.15em;text-transform:uppercase;margin:.75rem 0 .5rem;border-bottom:1px solid var(--border);padding-bottom:.4rem">${label} (${count})</div>`;
}

boot();
