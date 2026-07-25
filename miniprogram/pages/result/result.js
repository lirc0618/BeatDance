const { apiBase, request } = require('../../utils/api');

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
      comparisonUrl: result.comparison_image_url ? `${apiBase().replace('/api/v1', '')}${result.comparison_image_url}` : ''
    });
  },
  retry() {
    const result = this.data.result;
    wx.redirectTo({
      url: `/pages/upload/upload?actionId=${result.action_id}&name=${encodeURIComponent('同一动作二次验证')}&baselineId=${result.id}&focus=${result.diagnosis.user_focus || 'auto'}`
    });
  },
  restart() { wx.reLaunch({ url: '/pages/index/index' }); }
});
