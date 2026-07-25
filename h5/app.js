const API_BASE = (new URLSearchParams(location.search).get('api') || location.origin).replace(/\/$/, '');
const API = `${API_BASE}/api/v1`;
const MEDIA_ORIGIN = new URL(API_BASE, location.origin).origin;
const state = {
  actions: [], action: null, file: null, focus: 'auto',
  sessionId: localStorage.getItem('freezeCoachSession') || crypto.randomUUID(),
  baselineId: null, pausedAt: null, feedDuration: null, pauseInsight: null,
  actionSignature: '', actionsLoading: false, library: [], libraryLoading: false
};
localStorage.setItem('freezeCoachSession', state.sessionId);

const el = (id) => document.getElementById(id);
el('video-attribution').href = mediaUrl('/media/feed/ATTRIBUTION.md');
const sections = ['step-actions', 'step-insight', 'step-upload', 'loading', 'result'];
function show(id) {
  sections.forEach((name) => el(name).classList.toggle('hidden', name !== id));
  document.body.classList.toggle('flow-active', id !== 'step-actions');
  requestAnimationFrame(() => window.scrollTo({ top: id === 'step-actions' ? 0 : 54, behavior: 'auto' }));
}
function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[character]);
}
function safeUrl(value, base = MEDIA_ORIGIN) {
  try {
    const url = new URL(value, base);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
  } catch {
    return '';
  }
}
function mediaUrl(path) { return safeUrl(path); }
function formatTime(seconds) {
  const minutes = Math.floor(seconds / 60);
  const remainder = (seconds % 60).toFixed(1).padStart(4, '0');
  return `${String(minutes).padStart(2, '0')}:${remainder}`;
}

function adminToken() {
  const input = el('library-token');
  const value = input.value.trim();
  if (value) sessionStorage.setItem('duipaiAdminToken', value);
  return value;
}

function libraryCard(item) {
  const buttonCopy = item.imported ? '已经在首页' : (item.available ? '一键加入首页' : '素材待下载');
  return `
    <article class="library-card" data-sample-id="${escapeHtml(item.id)}">
      <video src="${escapeHtml(mediaUrl(item.preview_url))}" playsinline controls preload="none"></video>
      <div class="library-card-body">
        <div class="library-meta">
          <span>${escapeHtml(item.duration_label)} · ${escapeHtml(item.license_name)}</span>
          <a href="${escapeHtml(safeUrl(item.source_url))}" target="_blank" rel="noopener noreferrer">来源 ↗</a>
        </div>
        <strong>${escapeHtml(item.name)}</strong>
        <p>${escapeHtml(item.description)}</p>
        <small>${escapeHtml(item.creator)}</small>
        <button data-sample-id="${escapeHtml(item.id)}" ${item.imported || !item.available ? 'disabled' : ''}>${buttonCopy}</button>
      </div>
    </article>`;
}

function renderLibrary() {
  el('library-list').innerHTML = state.library.map(libraryCard).join('');
  document.querySelectorAll('.library-card button[data-sample-id]').forEach(button => {
    button.addEventListener('click', () => importSample(button.dataset.sampleId, button));
  });
}

async function loadLibrary() {
  if (state.libraryLoading) return;
  state.libraryLoading = true;
  el('library-message').textContent = '正在翻舞库…';
  try {
    const response = await fetch(`${API}/sample-library`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || '素材库加载失败');
    state.library = payload;
    renderLibrary();
    el('library-message').textContent = `${payload.length} 条可选素材，先试听再决定。`;
  } catch (error) {
    el('library-message').textContent = error.message;
  } finally {
    state.libraryLoading = false;
  }
}

async function importSample(sampleId, button) {
  const token = adminToken();
  if (!token) {
    el('library-message').textContent = '先填管理员口令，本地演示默认是 change-me。';
    el('library-token').focus();
    return;
  }
  button.disabled = true;
  button.textContent = '正在生成人体参考…';
  el('library-message').textContent = '正在转码、截取参考并提取骨架，通常需要几秒。';
  try {
    const response = await fetch(`${API}/sample-library/${encodeURIComponent(sampleId)}/import`, {
      method: 'POST',
      headers: { 'X-Admin-Token': token }
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || '加入首页失败');
    state.actionSignature = '';
    await Promise.all([loadActions(), loadLibrary()]);
    el('library-message').textContent = `“${payload.action.name}”已经加入首页，可以直接开刷。`;
  } catch (error) {
    button.disabled = false;
    button.textContent = '重新加入';
    el('library-message').textContent = error.message;
  }
}

function searchCards(results) {
  return results.map((item, index) => {
    const url = safeUrl(item.url);
    const isLocalVideo = Boolean(item.local_asset)
      || (url && new URL(url).pathname.startsWith('/media/tutorials/'));
    return `
    <article class="search-card ${isLocalVideo ? 'has-tutorial-video' : ''}">
      ${isLocalVideo ? `<video class="tutorial-video" src="${escapeHtml(url)}" controls playsinline preload="metadata"></video>` : ''}
      <div class="search-card-copy">
        <div class="rank">0${index + 1}</div>
        <span>${escapeHtml(item.view_type)}${item.clip_seconds ? ` · ${escapeHtml(item.clip_seconds)}` : ''}</span>
        <strong>${escapeHtml(item.title)}</strong>
        <small>${escapeHtml(item.why_matched || '这条正好对症')}</small>
        ${!isLocalVideo && url ? `<a class="search-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">打开原视频 ↗</a>` : ''}
      </div>
    </article>`;
  }).join('');
}

function actionSignature(actions) {
  return JSON.stringify(actions.map(action => [
    action.id, action.name, action.feed_video_url,
    action.reference_video_url, action.reference_ready
  ]));
}

async function loadActions() {
  if (state.actionsLoading) return;
  state.actionsLoading = true;
  let actions;
  try {
    const response = await fetch(`${API}/actions`);
    if (!response.ok) throw new Error('无法加载 Feed 片段');
    actions = await response.json();
  } finally {
    state.actionsLoading = false;
  }
  const signature = actionSignature(actions);
  if (signature === state.actionSignature) return;
  state.actionSignature = signature;
  state.actions = actions;
  el('action-count').textContent = String(state.actions.length);
  el('action-list').innerHTML = state.actions.map((action, index) => `
    <article class="feed-card" data-id="${escapeHtml(action.id)}">
      <div class="feed-visual visual-${index + 1} ${action.reference_ready ? 'has-video' : 'placeholder'}">
        ${action.reference_ready ? `<video class="feed-video" src="${escapeHtml(mediaUrl(action.feed_video_url || action.reference_video_url))}" playsinline controls preload="metadata"></video>` : ''}
        <span class="clip-label">${escapeHtml(action.segment_label || '动作片段')}</span>
        <b class="pause-mark">Ⅱ</b>
      </div>
      <div class="feed-body">
        <div class="feed-meta"><small>${escapeHtml(action.creator || '@创作者')}</small><i>0${index + 1}</i></div>
        <strong>${escapeHtml(action.feed_caption || action.name)}</strong>
        <p>${escapeHtml(action.description)}</p>
        <div class="pause-hint"><i></i>播放，停在没看懂的那一帧</div>
        <button data-id="${escapeHtml(action.id)}" disabled>
          ${action.reference_ready ? '播放视频，停在没看懂处' : '待配置参考片段'}
        </button>
      </div>
    </article>`).join('');
  document.querySelectorAll('.feed-card button[data-id]').forEach(button => {
    button.addEventListener('click', (event) => {
      event.stopPropagation();
      requestPauseInsight(button.dataset.id);
    });
  });
  document.querySelectorAll('.feed-card .feed-video').forEach(video => {
    const card = video.closest('.feed-card');
    const button = card.querySelector('button');
    video.addEventListener('play', () => {
      button.disabled = true;
      button.textContent = '看到没懂的地方就暂停';
    });
    video.addEventListener('pause', () => {
      if (video.ended || video.currentTime <= 0 || !Number.isFinite(video.duration)) return;
      card.dataset.pausedAt = String(video.currentTime);
      card.dataset.duration = String(video.duration);
      button.disabled = false;
      button.textContent = `分析 ${formatTime(video.currentTime)} 这一秒`;
    });
  });
}

el('open-library').addEventListener('click', async () => {
  el('sample-library').classList.remove('hidden');
  el('open-library').setAttribute('aria-expanded', 'true');
  await loadLibrary();
  el('sample-library').scrollIntoView({ behavior: 'smooth', block: 'start' });
});
el('close-library').addEventListener('click', () => {
  el('sample-library').classList.add('hidden');
  el('open-library').setAttribute('aria-expanded', 'false');
});

const savedAdminToken = sessionStorage.getItem('duipaiAdminToken');
el('library-token').value = savedAdminToken
  || (['localhost', '127.0.0.1'].includes(location.hostname) ? 'change-me' : '');

el('custom-import-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const token = adminToken();
  const file = el('custom-video').files[0];
  if (!token || !file) {
    el('library-message').textContent = '需要管理员口令和一个视频文件。';
    return;
  }
  const button = el('custom-import-button');
  const form = new FormData();
  form.append('video', file);
  form.append('action_id', `user_${Date.now().toString(36)}`);
  form.append('name', el('custom-name').value.trim());
  form.append('focus', el('custom-focus').value);
  const pauseAt = el('custom-pause-at').value;
  if (pauseAt) form.append('pause_at_seconds', pauseAt);
  button.disabled = true;
  button.textContent = '正在加入，请别关页面…';
  el('library-message').textContent = '正在处理本机视频，长视频会多等一会儿。';
  try {
    const response = await fetch(`${API}/actions/import`, {
      method: 'POST',
      headers: { 'X-Admin-Token': token },
      body: form
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || '视频导入失败');
    el('library-message').textContent = `“${payload.action.name}”已经加入首页。`;
    event.target.reset();
    state.actionSignature = '';
    await loadActions();
    el('library-message').textContent = `“${payload.action.name}”已经加入首页，可以直接开刷。`;
  } catch (error) {
    el('library-message').textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = '加入首页并生成分析参考';
  }
});

async function requestPauseInsight(id) {
  const card = Array.from(document.querySelectorAll('.feed-card')).find(
    item => item.dataset.id === id
  );
  if (!card) return;
  const pausedAt = Number(card.dataset.pausedAt);
  const duration = Number(card.dataset.duration);
  if (!Number.isFinite(pausedAt) || !Number.isFinite(duration)) return;
  state.action = state.actions.find(item => item.id === id);
  state.pausedAt = pausedAt;
  state.feedDuration = duration;
  el('loading-copy').textContent = '回看这一秒 → 找到谁先乱了 → 翻译成人话';
  show('loading');
  try {
    const response = await fetch(`${API}/actions/${id}/pause-insight`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ timestamp_seconds: pausedAt })
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || '暂停点分析失败');
    renderPauseInsight(payload);
  } catch (error) {
    alert(error.message);
    show('step-actions');
  }
}

function renderPauseInsight(insight) {
  state.pauseInsight = insight;
  const preview = el('pause-preview');
  preview.src = mediaUrl(state.action.feed_video_url || state.action.reference_video_url);
  preview.addEventListener('loadedmetadata', () => {
    preview.currentTime = insight.timestamp_seconds;
    preview.pause();
  }, { once: true });
  el('pause-time').textContent = `定格 ${formatTime(insight.timestamp_seconds)}`;
  el('pause-context').textContent = insight.observed_motion;
  el('pause-phase').textContent = insight.phase;
  el('pause-stuck').textContent = insight.likely_stuck_at;
  el('pause-watch').textContent = insight.watch_for;
  el('pause-search-results').innerHTML = searchCards(insight.search_results);
  show('step-insight');
}

function selectAction() {
  state.file = null;
  state.focus = state.pauseInsight?.suggested_focus || 'auto';
  document.querySelectorAll('#focus-chips button').forEach((button) => button.classList.toggle('active', button.dataset.focus === state.focus));
  el('selected-action').innerHTML = `
    <span>定格 ${formatTime(state.pausedAt)} · ${escapeHtml(state.pauseInsight.phase)}</span>
    <strong>${escapeHtml(state.action.name)}</strong>
    <p>${escapeHtml(state.pauseInsight.likely_stuck_at)}</p>`;
  el('video-input').value = '';
  el('video-preview').classList.add('hidden');
  el('analyze-button').disabled = true;
  show('step-upload');
}

document.querySelectorAll('#focus-chips button').forEach(button => button.addEventListener('click', () => {
  state.focus = button.dataset.focus;
  document.querySelectorAll('#focus-chips button').forEach(item => item.classList.toggle('active', item === button));
}));

el('video-input').addEventListener('change', (event) => {
  state.file = event.target.files[0];
  if (!state.file) return;
  el('video-preview').src = URL.createObjectURL(state.file);
  el('video-preview').classList.remove('hidden');
  el('upload-title').textContent = state.file.name;
  el('upload-hint').textContent = `${(state.file.size / 1024 / 1024).toFixed(1)} MB`;
  el('analyze-button').disabled = false;
});

async function analyze() {
  if (!state.file || !state.action) return;
  show('loading');
  const form = new FormData();
  form.append('video', state.file);
  form.append('action_id', state.action.id);
  form.append('session_id', state.sessionId);
  form.append('focus', state.focus);
  if (state.pausedAt !== null) {
    form.append('pause_timestamp_seconds', String(state.pausedAt));
  }
  if (state.baselineId) form.append('baseline_analysis_id', state.baselineId);
  try {
    const response = await fetch(`${API}/analyze`, { method: 'POST', body: form });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || '分析失败');
    renderResult(payload);
  } catch (error) {
    alert(error.message);
    show('step-upload');
  }
}

function renderResult(result) {
  const d = result.diagnosis;
  el('result-title').textContent = d.primary_error;
  document.querySelector('.result-kicker').textContent = d.status === 'aligned'
    ? '这把可以'
    : '一句话判定';
  el('result-feedback').textContent = d.vlm_summary || d.priority_feedback;
  el('drill').textContent = d.drill;
  const primaryMetrics = d.metrics.filter(item => item.kind === d.primary_metric);
  el('metric-grid').innerHTML = primaryMetrics.map(item => `
    <div class="metric">
      <span>${({timing:'出手时间', trajectory:'走的路线', angle:'摆的造型'})[item.kind]} · ${escapeHtml(item.body_part)}</span>
      <strong>${escapeHtml(item.human_value)}</strong>
      <div class="metric-track"><i style="width:${Math.round(item.normalized_score * 100)}%"></i></div>
    </div>`).join('');

  const comparisonVideo = el('comparison-video');
  const comparisonVideoWrap = el('comparison-video-wrap');
  if (result.comparison_video_url) {
    comparisonVideo.src = mediaUrl(result.comparison_video_url);
    el('analysis-replay-label').textContent =
      `整段分析 ${result.duration_seconds.toFixed(1)} 秒 · ${result.analyzed_frame_count} 帧 · 红色是卡点`;
    comparisonVideoWrap.classList.remove('hidden');
  } else {
    comparisonVideo.pause();
    comparisonVideo.removeAttribute('src');
    comparisonVideoWrap.classList.add('hidden');
  }

  const image = el('comparison-image');
  if (result.comparison_image_url) {
    image.src = mediaUrl(result.comparison_image_url);
    image.classList.remove('hidden');
  } else image.classList.add('hidden');

  const searchResults = d.search_results || (d.tutorial ? [d.tutorial] : []);
  el('search-results').innerHTML = searchCards(searchResults);

  el('improvement').classList.toggle('hidden', !result.improvement);
  if (result.improvement) el('improvement').textContent = result.improvement.message;
  el('warnings').innerHTML = (result.warnings || []).map(item => `<div>小提醒：${escapeHtml(item)}</div>`).join('');
  if (!state.baselineId) state.baselineId = result.id;
  show('result');
}

el('analyze-button').addEventListener('click', analyze);
el('practice-button').addEventListener('click', selectAction);
el('insight-back').addEventListener('click', () => show('step-actions'));
el('change-action').addEventListener('click', () => { state.baselineId = null; show('step-actions'); });
el('restart-button').addEventListener('click', () => { state.baselineId = null; show('step-actions'); });
el('retry-button').addEventListener('click', () => {
  state.file = null;
  el('video-input').value = '';
  el('video-preview').classList.add('hidden');
  el('upload-title').textContent = '上传第二次练习';
  el('upload-hint').textContent = '再来一遍，看看刚才那个卡壳点顺了没';
  el('analyze-button').disabled = true;
  show('step-upload');
});

loadActions().catch(error => {
  el('action-list').innerHTML = `<p>服务未连接：${escapeHtml(error.message)}<br>可用 ?api=https://你的域名 指定 API。</p>`;
});
setInterval(() => {
  if (document.visibilityState === 'visible'
      && !document.body.classList.contains('flow-active')) {
    loadActions().catch(() => {});
  }
}, 5000);
