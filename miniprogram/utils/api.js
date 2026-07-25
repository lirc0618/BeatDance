function apiBase() {
  return getApp().globalData.apiBase.replace(/\/$/, '');
}

function request(path, options = {}) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${apiBase()}${path}`,
      method: options.method || 'GET',
      data: options.data,
      header: options.header || {},
      timeout: 60000,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) resolve(res.data);
        else reject(new Error(res.data?.detail || `请求失败 ${res.statusCode}`));
      },
      fail: reject
    });
  });
}

function uploadAnalysis({ filePath, actionId, baselineId, focus = 'auto' }) {
  return new Promise((resolve, reject) => {
    const formData = {
      action_id: actionId,
      session_id: getApp().globalData.sessionId,
      focus
    };
    if (baselineId) formData.baseline_analysis_id = baselineId;
    wx.uploadFile({
      url: `${apiBase()}/analyze`,
      filePath,
      name: 'video',
      formData,
      timeout: 120000,
      success(res) {
        let data;
        try { data = JSON.parse(res.data); } catch (e) { return reject(new Error('服务返回格式异常')); }
        if (res.statusCode >= 200 && res.statusCode < 300) resolve(data);
        else reject(new Error(data.detail || `上传失败 ${res.statusCode}`));
      },
      fail: reject
    });
  });
}

module.exports = { request, uploadAnalysis, apiBase };
