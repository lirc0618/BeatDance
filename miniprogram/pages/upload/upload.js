const { uploadAnalysis } = require('../../utils/api');

Page({
  data: {
    actionId: '', actionName: '', segment: '', caption: '', filePath: '',
    analyzing: false, baselineId: '', focus: 'auto', pauseAt: '',
    focusOptions: [
      { id: 'auto', label: '我也说不清' },
      { id: 'upper', label: '手部没看懂' },
      { id: 'lower', label: '脚步没看懂' },
      { id: 'timing', label: '总跟不上拍' }
    ]
  },
  onLoad(options) {
    this.setData({
      actionId: options.actionId,
      actionName: decodeURIComponent(options.name || ''),
      segment: decodeURIComponent(options.segment || ''),
      caption: decodeURIComponent(options.caption || ''),
      baselineId: options.baselineId || '',
      focus: options.focus || 'auto',
      pauseAt: options.pauseAt || ''
    });
  },
  selectFocus(event) { this.setData({ focus: event.currentTarget.dataset.focus }); },
  chooseVideo() {
    wx.chooseMedia({
      count: 1,
      mediaType: ['video'],
      sourceType: ['album'],
      maxDuration: 8,
      success: res => this.setData({ filePath: res.tempFiles[0].tempFilePath }),
      fail: err => {
        if (!String(err.errMsg).includes('cancel')) wx.showToast({ title: '选择视频失败', icon: 'none' });
      }
    });
  },
  async analyze() {
    if (!this.data.filePath || this.data.analyzing) return;
    this.setData({ analyzing: true });
    try {
      const result = await uploadAnalysis({
        filePath: this.data.filePath,
        actionId: this.data.actionId,
        baselineId: this.data.baselineId,
        focus: this.data.focus,
        pauseAt: this.data.pauseAt
      });
      wx.setStorageSync(`analysis:${result.id}`, result);
      wx.redirectTo({ url: `/pages/result/result?id=${result.id}` });
    } catch (error) {
      wx.showModal({ title: '搜索失败', content: error.message, showCancel: false });
    } finally {
      this.setData({ analyzing: false });
    }
  }
});
