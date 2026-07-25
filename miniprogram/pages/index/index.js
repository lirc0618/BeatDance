const { request } = require('../../utils/api');

Page({
  data: { actions: [], loading: true, error: '' },
  onLoad() { this.loadActions(); },
  async loadActions() {
    this.setData({ loading: true, error: '' });
    try {
      const actions = await request('/actions');
      this.setData({ actions });
    } catch (error) {
      this.setData({ error: error.message });
    } finally {
      this.setData({ loading: false });
    }
  },
  chooseAction(event) {
    const actionId = event.currentTarget.dataset.id;
    const action = this.data.actions.find(item => item.id === actionId);
    if (!action.reference_ready) {
      wx.showToast({ title: '参考片段尚未配置', icon: 'none' });
      return;
    }
    wx.navigateTo({
      url: `/pages/upload/upload?actionId=${actionId}&name=${encodeURIComponent(action.name)}&segment=${encodeURIComponent(action.segment_label || '')}&caption=${encodeURIComponent(action.feed_caption || '')}`
    });
  }
});
