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

仓库当前已经生成 20 条有声拆解。需要从四条授权演示视频重新构建时，在项目
根目录执行：

```bash
make tutorial-build
```

服务端会把已登记文件映射为 `/media/tutorials/<tutorial-id>.mp4`，H5 与
小程序直接使用接口返回的 `url` 即可。
