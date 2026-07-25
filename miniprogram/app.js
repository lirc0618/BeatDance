App({
  globalData: {
    apiBase: 'https://YOUR_DOMAIN/api/v1',
    sessionId: ''
  },
  onLaunch() {
    let sessionId = wx.getStorageSync('freezeCoachSession');
    if (!sessionId) {
      sessionId = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
      wx.setStorageSync('freezeCoachSession', sessionId);
    }
    this.globalData.sessionId = sessionId;
  }
});
