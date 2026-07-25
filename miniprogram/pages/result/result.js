const { mediaUrl, request } = require('../../utils/api');

Page({
  data: {
    result: null, comparisonUrl: '', resultBadge: '你不是不会，只是卡在这一处',
    retryText: '练一次，再验证',
    metricLabels: { timing: '节奏', trajectory: '路线', angle: '幅度' }
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
    this.setData({
      result,
      resultBadge: result.diagnosis.status === 'aligned' ? '这一招已经很接近了' : '你不是不会，只是卡在这一处',
      retryText: result.diagnosis.status === 'aligned' ? '再录一次，确认稳定' : '练一次，再验证',
      comparisonUrl: mediaUrl(result.comparison_image_url)
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
        wx.showToast({ title: '链接已复制，请在抖音打开', icon: 'none' });
      }
    });
  },
  restart() { wx.reLaunch({ url: '/pages/index/index' }); }
});
