const { mediaUrl, request } = require('../../utils/api');

Page({
  data: {
    result: null, comparisonUrl: '', comparisonVideoUrl: '',
    resultBadge: '一句话判定', displayMetrics: [],
    retryText: '练一次，再验证',
    hasLocalTutorials: false,
    relatedOpen: false, relatedLoading: false, relatedStatus: '',
    relatedQuery: '', relatedVideos: [], relatedLaunches: [],
    metricLabels: { timing: '出手时间', trajectory: '走的路线', angle: '摆的造型' }
  },
  async onLoad(options) {
    let result = wx.getStorageSync(`analysis:${options.id}`);
    if (!result) {
      try { result = await request(`/results/${options.id}`); }
      catch (error) { return wx.showModal({ title: '加载失败', content: error.message, showCancel: false }); }
    }
    if (!result.diagnosis.search_results && result.diagnosis.tutorial) {
      result.diagnosis.search_results = [result.diagnosis.tutorial];
    }
    result.diagnosis.search_results = (result.diagnosis.search_results || []).map(item => ({
      ...item,
      url: mediaUrl(item.url)
    }));
    this.setData({
      result,
      hasLocalTutorials: result.diagnosis.search_results.length > 0
        && result.diagnosis.search_results.every(item => Boolean(item.local_asset)),
      displayMetrics: result.diagnosis.metrics.filter(
        item => item.kind === result.diagnosis.primary_metric
      ),
      resultBadge: result.diagnosis.status === 'aligned' ? '这把可以' : '一句话判定',
      retryText: result.diagnosis.status === 'aligned' ? '再录一次，确认稳定' : '练一次，再验证',
      comparisonUrl: mediaUrl(result.comparison_image_url),
      comparisonVideoUrl: mediaUrl(result.comparison_video_url)
    });
  },
  retry() {
    const result = this.data.result;
    wx.redirectTo({
      url: `/pages/upload/upload?actionId=${result.action_id}&name=${encodeURIComponent('同一动作二次验证')}&baselineId=${result.id}&focus=${result.diagnosis.user_focus || 'auto'}&pauseAt=${result.source_timestamp_seconds || ''}`
    });
  },
  openTutorial(event) {
    const url = event.currentTarget.dataset.url;
    if (!url) return wx.showToast({ title: '暂未配置内容链接', icon: 'none' });
    wx.setClipboardData({
      data: url,
      success() {
        wx.showToast({
          title: url.includes('/media/tutorials/')
            ? '教学视频链接已复制'
            : '链接已复制，请在抖音打开',
          icon: 'none'
        });
      }
    });
  },
  async searchRelated() {
    const { diagnosis } = this.data.result;
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
        `/actions/${this.data.result.action_id}/related-videos?metric=${diagnosis.primary_metric}&body_part=${encodeURIComponent(diagnosis.body_part || '')}&limit=6`
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
  },
  restart() { wx.reLaunch({ url: '/pages/index/index' }); }
});
