const API_BASE = (new URLSearchParams(location.search).get('api') || location.origin).replace(/\/$/, '');
const API = `${API_BASE}/api/v1`;
const MEDIA_ORIGIN = new URL(API_BASE, location.origin).origin;
const state = {
  actions: [], action: null, file: null, focus: 'auto',
  sessionId: localStorage.getItem('freezeCoachSession') || crypto.randomUUID(),
  baselineId: null, pausedAt: null, feedDuration: null, pauseInsight: null,
  actionSignature: '', actionsLoading: false, library: [], libraryLoading: false,
  relatedMetric: 'trajectory', relatedBodyPart: '', scanTimer: null,
  lastResultWasRetry: false, baselineReplayUrl: ''
};
localStorage.setItem('freezeCoachSession', state.sessionId);

const el = (id) => document.getElementById(id);
el('video-attribution').href = mediaUrl('/media/feed/ATTRIBUTION.md');
const sections = ['step-actions', 'step-insight', 'step-upload', 'loading', 'result'];
const scanCopies = [
  '正在捕捉动作轨迹',
  '把你的动作对齐到原拍',
  '只找这局最大的偏差',
  '正在配一条最短解法'
];

function stopScanSequence() {
  if (state.scanTimer) window.clearInterval(state.scanTimer);
  state.scanTimer = null;
}

function startScanSequence() {
  stopScanSequence();
  let scanIndex = 0;
  const steps = Array.from(document.querySelectorAll('.scan-step'));
  const update = () => {
    steps.forEach((step, index) => {
      step.classList.toggle('active', index === scanIndex);
      step.classList.toggle('done', index < scanIndex);
    });
    el('loading-copy').textContent = scanCopies[scanIndex];
    scanIndex = Math.min(scanIndex + 1, steps.length - 1);
  };
  update();
  state.scanTimer = window.setInterval(update, 900);
}

function currentPhase(id) {
  if (id === 'step-upload') return state.baselineId ? 'rematch' : 'challenge';
  if (id === 'loading') return state.baselineId ? 'rematch' : 'decode';
  if (id === 'result') return state.lastResultWasRetry ? 'rematch' : 'decode';
  return 'lock';
}

function show(id) {
  if (id === 'loading') startScanSequence();
  else stopScanSequence();
  sections.forEach((name) => el(name).classList.toggle('hidden', name !== id));
  const phase = currentPhase(id);
  document.querySelectorAll('.mission-step').forEach(step => {
    const phases = ['lock', 'challenge', 'decode', 'rematch'];
    const active = step.dataset.phase === phase;
    step.classList.toggle('active', active);
    step.classList.toggle('done', phases.indexOf(step.dataset.phase) < phases.indexOf(phase));
    if (active) step.setAttribute('aria-current', 'step');
    else step.removeAttribute('aria-current');
  });
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

function syncFocusControls() {
  document.querySelectorAll('.focus-control button').forEach(button => {
    const active = button.dataset.focus === state.focus;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
}

function actionFocus(action) {
  const copy = `${action.name} ${action.description} ${action.feed_caption}`.toLowerCase();
  if (/脚|腿|步|feet|foot|jump|科目三/.test(copy)) return '脚下关';
  if (/手|臂|肩|upper|hand|爱你/.test(copy)) return '上身关';
  if (/节奏|卡点|摇|timing|beat/.test(copy)) return '节奏关';
  return '全身关';
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
    <article class="search-card ${isLocalVideo ? 'has-tutorial-video' : ''}" data-loadout="${index + 1}">
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

function relatedVideoCards(videos) {
  return videos.map((item) => {
    const videoUrl = safeUrl(item.url);
    const coverUrl = safeUrl(item.cover_url);
    if (!videoUrl) return '';
    return `
      <article class="external-video-card">
        ${coverUrl
          ? `<img src="${escapeHtml(coverUrl)}" alt="" loading="lazy" />`
          : '<div class="external-cover-placeholder">▶</div>'}
        <div>
          <span>抖音 · ${Number(item.like_count || 0).toLocaleString('zh-CN')} 赞</span>
          <strong>${escapeHtml(item.title)}</strong>
          <small>${escapeHtml(item.creator || '抖音创作者')}</small>
          <a href="${escapeHtml(videoUrl)}" target="_blank" rel="noopener noreferrer">去原平台看 ↗</a>
        </div>
      </article>`;
  }).join('');
}

function relatedLaunches(launches) {
  return launches.map((item) => {
    const url = safeUrl(item.url);
    return url
      ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.label)} ↗</a>`
      : '';
  }).join('');
}

function renderTutorialSource(prefix, results) {
  const localCount = results.filter(item => Boolean(item.local_asset)).length;
  if (localCount === results.length && localCount > 0) {
    el(`${prefix}-tutorial-source`).textContent = 'AI 即时拆解 · 取自当前视频';
    el(`${prefix}-tutorial-title`).textContent =
      prefix === 'pause' ? '同源慢放、镜像和局部' : '三条对症拆法';
  } else {
    el(`${prefix}-tutorial-source`).textContent = '搜索方向 · 不是当前视频生成';
    el(`${prefix}-tutorial-title`).textContent = '先看该找哪种视角';
  }
}

async function openRelatedVideos() {
  if (!state.action) return;
  const dialog = el('related-video-dialog');
  el('related-status').textContent = '正在按你的卡点翻相关教学…';
  el('related-query').textContent = '';
  el('external-video-results').innerHTML = '<div class="related-loading">搜索中 ···</div>';
  el('related-launches').innerHTML = '';
  if (!dialog.open) dialog.showModal();

  const params = new URLSearchParams({
    metric: state.relatedMetric,
    body_part: state.relatedBodyPart,
    limit: '6'
  });
  try {
    const response = await fetch(
      `${API}/actions/${encodeURIComponent(state.action.id)}/related-videos?${params}`
    );
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || '相关视频搜索失败');
    el('related-status').textContent = payload.message;
    el('related-query').textContent = `这次搜：${payload.query}`;
    el('external-video-results').innerHTML = payload.videos.length
      ? relatedVideoCards(payload.videos)
      : '<div class="related-empty">接口暂时没返回视频卡片，下面的抖音精准搜索入口照样能用。</div>';
    el('related-launches').innerHTML = relatedLaunches(payload.launches);
  } catch (error) {
    el('related-status').textContent = error.message;
    el('external-video-results').innerHTML =
      '<div class="related-empty">外部搜索开小差了，关掉窗口后可以继续当前练习。</div>';
  }
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
        <span class="level-focus">${actionFocus(action)}</span>
        <strong>${escapeHtml(action.feed_caption || action.name)}</strong>
        <p>${escapeHtml(action.description)}</p>
        <div class="mini-wave" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>
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
  const button = card.querySelector('button');
  const buttonCopy = button.textContent;
  button.disabled = true;
  button.textContent = '正在锁定这一拍…';
  try {
    const response = await fetch(`${API}/actions/${id}/pause-insight`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ timestamp_seconds: pausedAt })
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || '暂停点分析失败');
    button.disabled = false;
    button.textContent = buttonCopy;
    renderPauseInsight(payload);
  } catch (error) {
    button.disabled = false;
    button.textContent = buttonCopy;
    alert(error.message);
    show('step-actions');
  }
}

function renderPauseInsight(insight) {
  state.pauseInsight = insight;
  state.focus = insight.suggested_focus || 'auto';
  syncFocusControls();
  const firstMatch = insight.search_results?.[0];
  state.relatedMetric = ['timing', 'trajectory', 'angle'].includes(firstMatch?.error_type)
    ? firstMatch.error_type
    : 'trajectory';
  state.relatedBodyPart = firstMatch?.body_part || '';
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
  const duration = Number(insight.feed_duration_seconds || state.feedDuration);
  const lockPercent = Number.isFinite(duration) && duration > 0
    ? Math.max(8, Math.min(92, (insight.timestamp_seconds / duration) * 100))
    : 50;
  el('pause-beat-lane').style.setProperty('--lock-position', `${lockPercent}%`);
  el('pause-search-results').innerHTML = searchCards(insight.search_results);
  renderTutorialSource('pause', insight.search_results);
  show('step-insight');
}

function selectAction() {
  state.file = null;
  syncFocusControls();
  el('selected-action').innerHTML = `
    <span>定格 ${formatTime(state.pausedAt)} · ${escapeHtml(state.pauseInsight.phase)}</span>
    <strong>${escapeHtml(state.action.name)}</strong>
    <p>${escapeHtml(state.pauseInsight.likely_stuck_at)}</p>`;
  el('video-input').value = '';
  el('video-preview').classList.add('hidden');
  document.querySelector('.challenge-stage').classList.remove('has-file');
  el('analyze-button').disabled = true;
  show('step-upload');
}

document.querySelectorAll('.focus-control button').forEach(button => button.addEventListener('click', () => {
  state.focus = button.dataset.focus;
  syncFocusControls();
}));

el('video-input').addEventListener('change', (event) => {
  state.file = event.target.files[0];
  if (!state.file) return;
  el('video-preview').src = URL.createObjectURL(state.file);
  el('video-preview').classList.remove('hidden');
  document.querySelector('.challenge-stage').classList.add('has-file');
  el('upload-title').textContent = state.file.name;
  el('upload-hint').textContent = `${(state.file.size / 1024 / 1024).toFixed(1)} MB`;
  el('analyze-button').disabled = false;
});

async function analyze() {
  if (!state.file || !state.action) return;
  const wasRetry = Boolean(state.baselineId);
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
    renderResult(payload, wasRetry);
  } catch (error) {
    alert(error.message);
    show('step-upload');
  }
}

function renderResult(result, wasRetry = false) {
  const d = result.diagnosis;
  state.lastResultWasRetry = wasRetry;
  state.relatedMetric = d.primary_metric;
  state.relatedBodyPart = d.body_part || '';
  el('result-title').textContent = d.primary_error;
  const improved = Boolean(result.improvement?.improved);
  const judgement = d.status === 'aligned' || improved
    ? 'CLEAR'
    : (result.improvement ? 'ALMOST' : 'MISS');
  const judgementNode = el('result-judgement');
  judgementNode.textContent = judgement;
  judgementNode.className = `result-judgement ${judgement.toLowerCase()}`;
  document.querySelector('.result-kicker').textContent = d.status === 'aligned'
    ? '这一拍已经过关'
    : (result.improvement ? '再战判定' : '本局 Boss 已锁定');
  el('result-feedback').textContent = d.vlm_summary || d.priority_feedback;
  el('drill').textContent = d.drill;
  const primaryMetrics = d.metrics.filter(item => item.kind === d.primary_metric);
  el('metric-grid').innerHTML = primaryMetrics.map(item => `
    <div class="metric">
      <span>${({timing:'出手时间', trajectory:'走的路线', angle:'摆的造型'})[item.kind]} · ${escapeHtml(item.body_part)}</span>
      <strong>${escapeHtml(item.human_value)}</strong>
      <div class="metric-track"><i style="width:${Math.round(item.normalized_score * 100)}%"></i></div>
    </div>`).join('');
  const lockedPercent = Number.isFinite(state.pausedAt) && state.feedDuration > 0
    ? Math.max(0, Math.min(1, state.pausedAt / state.feedDuration))
    : 0.5;
  const missIndex = Math.round(lockedPercent * 3);
  document.querySelectorAll('#result-beat-lane .beat-node').forEach((node, index) => {
    node.classList.remove('miss', 'great', 'perfect');
    if (judgement !== 'CLEAR' && index === missIndex) {
      node.classList.add('miss');
      node.querySelector('span').textContent = 'MISS';
    } else {
      node.classList.add(index === 0 ? 'perfect' : 'great');
      node.querySelector('span').textContent = index === 0 ? 'PERFECT' : 'GREAT';
    }
  });
  el('result-lane-summary').textContent = judgement === 'CLEAR'
    ? '这一拍已全线通过'
    : `卡点在动作 ${Math.round(lockedPercent * 100)}% 处`;

  const comparisonVideo = el('comparison-video');
  const comparisonVideoWrap = el('comparison-video-wrap');
  const baselineVideo = el('baseline-comparison-video');
  const baselineVideoWrap = el('baseline-comparison-wrap');
  if (result.improvement && state.baselineReplayUrl) {
    baselineVideo.src = state.baselineReplayUrl;
    baselineVideoWrap.classList.remove('hidden');
  } else {
    baselineVideo.pause();
    baselineVideo.removeAttribute('src');
    baselineVideoWrap.classList.add('hidden');
  }
  if (result.comparison_video_url) {
    const replayUrl = mediaUrl(result.comparison_video_url);
    comparisonVideo.src = replayUrl;
    el('analysis-replay-label').textContent =
      `${result.improvement ? '再练' : '本局'}匿名骨架 · ${result.duration_seconds.toFixed(1)} 秒 · ${result.analyzed_frame_count} 帧`;
    comparisonVideoWrap.classList.remove('hidden');
    if (!state.baselineId) state.baselineReplayUrl = replayUrl;
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
  renderTutorialSource('result', searchResults);

  el('improvement').classList.toggle('hidden', !result.improvement);
  if (result.improvement) el('improvement').textContent = result.improvement.message;
  el('warnings').innerHTML = (result.warnings || []).map(item => `<div>小提醒：${escapeHtml(item)}</div>`).join('');
  if (!state.baselineId) state.baselineId = result.id;
  show('result');
}

el('analyze-button').addEventListener('click', analyze);
el('pause-related-button').addEventListener('click', openRelatedVideos);
el('result-related-button').addEventListener('click', openRelatedVideos);
el('related-close').addEventListener('click', () => el('related-video-dialog').close());
el('related-video-dialog').addEventListener('click', (event) => {
  if (event.target === el('related-video-dialog')) el('related-video-dialog').close();
});
el('practice-button').addEventListener('click', selectAction);
el('insight-back').addEventListener('click', () => show('step-actions'));
el('change-action').addEventListener('click', () => {
  state.baselineId = null;
  state.baselineReplayUrl = '';
  show('step-actions');
});
el('restart-button').addEventListener('click', () => {
  state.baselineId = null;
  state.baselineReplayUrl = '';
  show('step-actions');
});
el('retry-button').addEventListener('click', () => {
  state.file = null;
  el('video-input').value = '';
  el('video-preview').classList.add('hidden');
  document.querySelector('.challenge-stage').classList.remove('has-file');
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
