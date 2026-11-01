# 小窝聊天（PluginChat）

Halo 插件 `PluginChat`（displayName：小窝聊天，v0.2.0）+ 配套的聊天室后端 / 前端工程。

## 功能
- Halo 插件：在 UC 个人中心侧边栏加入「小窝聊天」入口，跳转 `sams-house.top/chat` 独立聊天页（非 iframe 内嵌）。
- 聊天室后端：基于 Python 标准库 + SQLite + 手写 WebSocket，支持群聊 / 私聊、撤回、已读回执、@提及、消息持久化等。
- 前端：`static/index.html` 单页聊天界面 + 插件 UI（`plugin/ui`，Vue + Vite）。

## 目录结构
- `plugin/` —— Halo 插件本体（Java 源码、`plugin.yaml`、console 资源、UI 前端）
- `server.py` —— 聊天室后端服务
- `static/` —— 聊天室前端页面
- `*.py` / `*.js` —— 部署、运维与接口/UI 测试脚本
- `ui-plugin/` —— 侧边栏入口相关配置
- `uploads-nginx-block.conf` —— 上传相关 nginx 配置片段

## 部署
1. 打包插件：`plugin/build.py` / `plugin/pack.py`
2. 安装插件：`plugin/install.py`
3. 启动聊天室：`server.py`（默认 8322，配合 nginx `/chat/` + `/chat/ws`）
4. 发布 / 推静态资源：`publish.py` / `push-static.py`

## 说明
本仓库由本地工程导入，构建产物（`node_modules/`、`build/`、`dist/*.jar`）、数据库（`.db`）、截图（`.png`）等已通过 `.gitignore` 排除。
