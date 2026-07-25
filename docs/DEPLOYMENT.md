# 部署说明

## 服务器建议

- Ubuntu 22.04/24.04
- 4 核 CPU、8GB 内存
- Docker 与 Docker Compose
- HTTPS 域名
- 至少 20GB 磁盘

MVP 使用单 Uvicorn Worker，避免本地文件与多进程状态不一致。并发扩展时再引入对象存储和任务队列。

## 部署

```bash
git clone <repo>
cd dingge-coach
cp .env.example .env
vim .env
docker compose up --build -d
```

`.env` 中的 `ADMIN_TOKEN` 必须显式填写至少 24 字符的随机值；空值、默认值和
文档占位值都不会开启管理员写接口。

反向代理示例（Nginx）：

```nginx
server {
  listen 443 ssl http2;
  server_name coach.example.com;
  client_max_body_size 220m;

  location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 360s;
  }
}
```

## 豆包

在火山方舟创建支持文本对话的模型推理接入点，填入：

```env
ARK_API_KEY=...
ARK_MODEL=ep-xxxxxxxx
```

当前代码调用兼容 Chat Completions 的 `/chat/completions`。建议使用支持视觉理解的豆包模型接入点；系统会发送关键帧对比图与结构化诊断进行核验。API 失败会回退到规则模板。

本地教学视频随镜像复制到 `/app/assets/tutorials`，可通过
`TUTORIAL_ASSETS_DIR` 覆盖。目录中已登记的文件由 `/media/tutorials/` 提供访问。

部署前必须在 `.env` 设置非默认的长随机 `ADMIN_TOKEN`。默认值 `change-me`
会禁用 Feed 导入和参考视频更新接口，避免公网实例被任意写入。

## 参考动作

服务启动后为每个动作上传标准视频：

```bash
python scripts/register_reference.py \
  --api https://coach.example.com/api/v1 \
  --token "$ADMIN_TOKEN" \
  --action groove_step \
  --video ./assets/references/groove_step.mp4
```

标准视频必须与用户拍摄规范一致。

## 微信配置

- 将 `https://coach.example.com` 加入 request 合法域名；
- 将同域名加入 uploadFile 合法域名；
- 域名必须 HTTPS 且证书有效；
- 修改 `miniprogram/app.js` 的 `apiBase`；
- 比赛前发布体验版，并给所有评委手机准备 H5 备用。

## 数据生命周期

默认：

- 用户原始视频：分析结束即删除；
- 参考视频：长期保存；
- 结果 JSON/对比图：保存到 Docker Volume；
- 比赛后可通过定时任务清理 7 天前结果。
