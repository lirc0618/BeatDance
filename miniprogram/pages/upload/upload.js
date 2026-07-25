const { uploadAnalysis } = require('../../utils/api');

Page({
  data: {
    actionId: '', actionName: '', segment: '', caption: '', filePath: '',
    analyzing: false, baselineId: '', focus: 'auto', pauseAt: '',
    focusOptions: [
      { id: 'auto', label: 'AI 选重点' },
      { id: 'hands', label: '看手势' },
      { id: 'arms', label: '看手臂' },
      { id: 'torso', label: '看核心' },
      { id: 'lower', label: '看脚步' },
      { id: 'timing', label: '卡节奏' }
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
      sourceType: ['album', 'camera'],
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
      const mismatch = /动作.*对不上|更像《.+》.*不是当前/.test(error.message);
      wx.showModal({
        title: mismatch ? '这段先不分析' : '暂时看不清',
        content: error.message,
        showCancel: false
      });
    } finally {
      this.setData({ analyzing: false });
    }
  }
});
