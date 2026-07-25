const { mediaUrl, request } = require('../../utils/api');

function formatTime(seconds) {
  const whole = Math.max(0, Math.floor(seconds));
  const minutes = String(Math.floor(whole / 60)).padStart(2, '0');
  const remainder = String(whole % 60).padStart(2, '0');
  return `${minutes}:${remainder}`;
}

Page({
  data: {
    actions: [], loading: true, error: '', insight: null, selectedAction: null,
    relatedOpen: false, relatedLoading: false, relatedStatus: '',
    relatedQuery: '', relatedVideos: [], relatedLaunches: []
  },
  onLoad() {
    this.feedTimes = {};
    this.actionSignature = '';
    this.actionsLoading = false;
  },
  onShow() {
    this.loadActions();
    this.actionPoll = setInterval(() => {
      if (!this.data.insight) this.loadActions({ silent: true });
    }, 5000);
  },
  onHide() {
    clearInterval(this.actionPoll);
  },
  onUnload() {
    clearInterval(this.actionPoll);
  },
  async loadActions({ silent = false } = {}) {
    if (this.actionsLoading) return;
    this.actionsLoading = true;
    if (!silent) this.setData({ loading: true, error: '' });
    try {
      const actions = (await request('/actions')).map(action => ({
        ...action,
        feed_video_full_url: (action.feed_video_url || action.reference_video_url)
          ? mediaUrl(action.feed_video_url || action.reference_video_url)
          : ''
      }));
      const signature = JSON.stringify(actions.map(action => [
        action.id,
        action.name,
        action.feed_video_url,
        action.reference_video_url,
        action.reference_ready
      ]));
      if (signature !== this.actionSignature) {
        this.actionSignature = signature;
        this.setData({ actions });
      }
    } catch (error) {
      if (!silent) this.setData({ error: error.message });
    } finally {
      this.actionsLoading = false;
      if (!silent) this.setData({ loading: false });
    }
  },
  trackFeedTime(event) {
    this.feedTimes[event.currentTarget.dataset.id] = {
      timestamp: event.detail.currentTime,
      duration: event.detail.duration
    };
  },
  pauseFeed(event) {
    const actionId = event.currentTarget.dataset.id;
    const point = this.feedTimes[actionId];
    const eventTimestamp = Number(event.detail?.currentTime);
    const timestamp = Number.isFinite(eventTimestamp) && eventTimestamp > 0
      ? eventTimestamp
      : Number(point?.timestamp);
    if (!Number.isFinite(timestamp) || timestamp <= 0) return;
    const index = this.data.actions.findIndex(item => item.id === actionId);
    this.setData({
      [`actions[${index}].pauseReady`]: true,
      [`actions[${index}].pauseCopy`]: `分析 ${formatTime(timestamp)} 这一秒`,
      [`actions[${index}].pausedAt`]: timestamp
    });
  },
  async chooseAction(event) {
    const actionId = event.currentTarget.dataset.id;
    const action = this.data.actions.find(item => item.id === actionId);
    if (!action.reference_ready) {
      wx.showToast({ title: '参考片段尚未配置', icon: 'none' });
      return;
    }
    if (!action.pauseReady) return;
    this.setData({ loading: true, error: '' });
    try {
      const insight = await request(`/actions/${actionId}/pause-insight`, {
        method: 'POST',
        data: {
          timestamp_seconds: action.pausedAt
        }
      });
      insight.search_results = (insight.search_results || []).map(item => ({
        ...item,
        url: mediaUrl(item.url)
      }));
      insight.has_local_tutorials = insight.search_results.length > 0
        && insight.search_results.every(item => Boolean(item.local_asset));
      this.setData({ insight, selectedAction: action });
    } catch (error) {
      this.setData({ error: error.message });
    } finally {
      this.setData({ loading: false });
    }
  },
  startPractice() {
    const { selectedAction: action, insight } = this.data;
    wx.navigateTo({
      url: `/pages/upload/upload?actionId=${action.id}&name=${encodeURIComponent(action.name)}&segment=${encodeURIComponent(`${insight.timestamp_seconds.toFixed(1)} 秒 · ${insight.phase}`)}&caption=${encodeURIComponent(insight.likely_stuck_at)}&focus=${insight.suggested_focus}&pauseAt=${insight.timestamp_seconds}`
    });
  },
  backToFeed() {
    this.setData({ insight: null, selectedAction: null });
  },
  copySearch(event) {
    const url = event.currentTarget.dataset.url;
    if (!url) return;
    wx.setClipboardData({ data: url });
  },
  async searchRelated() {
    const { insight, selectedAction } = this.data;
    const first = insight.search_results?.[0] || {};
    const metric = ['timing', 'trajectory', 'angle'].includes(first.error_type)
      ? first.error_type
      : 'trajectory';
    this.setData({
      relatedOpen: true,
      relatedLoading: true,
      relatedStatus: '正在按你的卡点翻相关教学…',
      relatedQuery: '',
      relatedVideos: [],
      relatedLaunches: []
    });
    try {
      const payload = await request(
        `/actions/${selectedAction.id}/related-videos?metric=${metric}&body_part=${encodeURIComponent(first.body_part || '')}&limit=6`
      );
      this.setData({
        relatedStatus: payload.message,
        relatedQuery: payload.query,
        relatedVideos: payload.videos || [],
        relatedLaunches: payload.launches || []
      });
    } catch (error) {
      this.setData({ relatedStatus: error.message });
    } finally {
      this.setData({ relatedLoading: false });
    }
  },
  closeRelated() {
    this.setData({ relatedOpen: false });
  },
  copyExternal(event) {
    const url = event.currentTarget.dataset.url;
    if (!url) return;
    wx.setClipboardData({
      data: url,
      success() {
        wx.showToast({ title: '链接已复制', icon: 'none' });
      }
    });
  },
  noop() {
  }
});
