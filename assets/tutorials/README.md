# 本地教学视频

已获得本地保存许可的教学视频放在本目录，并按
`backend/app/data/tutorial_catalog.json` 中的教学记录 `id` 命名：

```text
assets/tutorials/<tutorial-id>.mp4
```

例如：

```text
assets/tutorials/aini-mirror.mp4
assets/tutorials/kemusan-feet.mp4
assets/tutorials/shake-upper.mp4
assets/tutorials/jumpstyle-feet.mp4
```

文件就位后，将相对项目根目录的路径写入对应记录的 `local_asset`。文件尚未
准备时保留空字符串；不要填写不存在的路径。

服务端会把已登记文件映射为 `/media/tutorials/<tutorial-id>.mp4`，H5 与
小程序直接使用接口返回的 `url` 即可。
