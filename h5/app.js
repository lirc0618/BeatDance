const API = (new URLSearchParams(location.search).get('api') || '').replace(/\/$/, '') + '/api/v1';
const state = {
  actions: [], action: null, file: null, focus: 'auto',
  sessionId: localStorage.getItem('freezeCoachSession') || crypto.randomUUID(),
  baselineId: null
};
localStorage.setItem('freezeCoachSession', state.sessionId);

const el = (id) => document.getElementById(id);
const sections = ['step-actions', 'step-upload', 'loading', 'result'];
function show(id) { sections.forEach((name) => el(name).classList.toggle('hidden', name !== id)); }
function mediaUrl(path) { return path?.startsWith('http') ? path : `${location.origin}${path}`; }

async function loadActions() {
  const response = await fetch(`${API}/actions`);
  if (!response.ok) throw new Error('无法加载 Feed 片段');
  state.actions = await response.json();
  el('action-list').innerHTML = state.actions.map((action, index) => `
    <article class="feed-card" data-id="${action.id}">
      <div class="feed-visual visual-${index + 1}">
        <span>${action.segment_label || '动作片段'}</span>
        <b>Ⅱ</b>
      </div>
      <div class="feed-body">
        <small>${action.creator || '@创作者'}</small>
        <strong>${action.feed_caption || action.name}</strong>
        <p>${action.description}</p>
        <button data-id="${action.id}" ${action.reference_ready ? '' : 'disabled'}>
          ${action.reference_ready ? (action.entry_copy || '定格学这一招') : '待配置参考片段'}
        </button>
      </div>
    </article>`).join('');
  document.querySelectorAll('.feed-card button:not(:disabled)').forEach(button => {
    button.addEventListener('click', (event) => {
      event.stopPropagation();
      selectAction(button.dataset.id);
    });
  });
}

function selectAction(id) {
  state.action = state.actions.find(item => item.id === id);
  state.file = null;
  state.focus = 'auto';
  document.querySelectorAll('#focus-chips button').forEach((button) => button.classList.toggle('active', button.dataset.focus === 'auto'));
  el('selected-action').innerHTML = `
    <span>${state.action.segment_label}</span>
    <strong>${state.action.name}</strong>
    <p>${state.action.feed_caption}</p>`;
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
    ? '这一招已经很接近了'
    : '你不是不会，只是卡在这一处';
  el('result-feedback').textContent = d.vlm_summary || d.priority_feedback;
  el('drill').textContent = d.drill;
  el('search-query').textContent = d.search_query || '';
  el('metric-grid').innerHTML = d.metrics.map(item => `
    <div class="metric">
      <span>${({timing:'节奏', trajectory:'路线', angle:'幅度'})[item.kind]} · ${item.body_part}</span>
      <strong>${item.human_value}</strong>
      <div class="metric-track"><i style="width:${Math.round(item.normalized_score * 100)}%"></i></div>
    </div>`).join('');

  const image = el('comparison-image');
  if (result.comparison_image_url) {
    image.src = mediaUrl(result.comparison_image_url);
    image.classList.remove('hidden');
  } else image.classList.add('hidden');

  const searchResults = d.search_results || (d.tutorial ? [d.tutorial] : []);
  el('search-results').innerHTML = searchResults.map((item, index) => `
    <article class="search-card">
      <div class="rank">0${index + 1}</div>
      <div>
        <span>${item.view_type}${item.clip_seconds ? ` · ${item.clip_seconds}` : ''}</span>
        <strong>${item.title}</strong>
        <p>${item.description}</p>
        <small>${item.why_matched || '与当前卡点匹配'}${item.creator ? ` · ${item.creator}` : ''}</small>
      </div>
    </article>`).join('');

  el('improvement').classList.toggle('hidden', !result.improvement);
  if (result.improvement) el('improvement').textContent = result.improvement.message;
  el('warnings').innerHTML = (result.warnings || []).map(item => `<div>提示：${item}</div>`).join('');
  if (!state.baselineId) state.baselineId = result.id;
  show('result');
}

el('analyze-button').addEventListener('click', analyze);
el('change-action').addEventListener('click', () => { state.baselineId = null; show('step-actions'); });
el('restart-button').addEventListener('click', () => { state.baselineId = null; show('step-actions'); });
el('retry-button').addEventListener('click', () => {
  state.file = null;
  el('video-input').value = '';
  el('video-preview').classList.add('hidden');
  el('upload-title').textContent = '上传第二次练习';
  el('upload-hint').textContent = '系统会验证刚才的卡点是否改善';
  el('analyze-button').disabled = true;
  show('step-upload');
});

loadActions().catch(error => {
  el('action-list').innerHTML = `<p>服务未连接：${error.message}<br>可用 ?api=https://你的域名 指定 API。</p>`;
});
