# 心屿 Xinyu 部署说明

心屿是 Next.js + FastAPI + SQLite 的全栈应用，**不能作为纯静态站点完整运行**。
推荐把前后端打进同一个 Docker 容器，挂载持久磁盘保存 SQLite 数据，对外只暴露 3000 端口。

## 方式一：Railway（推荐，一个服务一个网址）

1. 用 GitHub 登录 Railway，新建项目并选择本仓库；
2. Railway 会自动识别根目录 `Dockerfile`（也可手动选择 Dockerfile builder）；
3. 添加 Volume，挂载路径填 `/data`（SQLite 与备份会写入这里）；
4. 配置环境变量：
   - `MODELSCOPE_API_KEY`（必填）
   - `SECRET_KEY`（建议随机长字符串）
   - `DATABASE_URL=sqlite:////data/xinyu.db`
   - `MODELSCOPE_BASE_URL` / `CHAT_MODEL` / `EMBEDDING_MODEL` / `VISION_MODEL`（可选，有默认值）
5. 部署完成后 Railway 会给出 `https://xxx.up.railway.app`，所有人可访问；
6. 之后每次 `git push` 自动重新部署，数据在 Volume 中保留。

## 方式二：Render（Docker + 持久磁盘）

1. 用 GitHub 登录 Render，New → Web Service，选择本仓库；
2. Runtime 选 Docker，Dockerfile 路径 `./Dockerfile`；
3. 计划选择带 Persistent Disk 的实例，磁盘挂载路径 `/data`，大小 1GB 起；
4. 环境变量同上（`DATABASE_URL=sqlite:////data/xinyu.db`）；
5. 也可以直接用仓库根目录的 `render.yaml` Blueprint 一键创建；
6. Health Check 路径 `/health`。

> 注意：Render 免费实例没有持久磁盘，重启/重新部署会丢失数据，正式使用请选带磁盘的计划。

## 方式三：Vercel（前端）+ Render/Railway（后端）

1. 后端按上面方式部署，得到 `https://<backend-domain>`；
2. Vercel 导入仓库，Root Directory 选 `frontend`，Framework 选 Next.js；
3. 在 Vercel 环境变量里添加 `BACKEND_URL=https://<backend-domain>`；
4. 前端通过 Next rewrites 把 `/api/*`、`/health` 反向代理到后端，无需改前端代码；
5. 后端设置 `CORS_ORIGINS=https://<vercel-domain>`（多个用逗号分隔）。

## 本地验证容器

```bash
docker build -t xinyu:latest .
docker run --rm -p 3000:3000 -v xinyu-data:/data \
  -e MODELSCOPE_API_KEY=<your-key> \
  -e SECRET_KEY=<random-secret> \
  xinyu:latest
```

打开 http://localhost:3000 即可。

## 必需依赖清单

| 依赖 | 说明 |
| --- | --- |
| Python 3.13 + FastAPI | 容器内运行，提供全部 `/api` |
| Node 20 + Next.js 16 | 容器内运行，提供页面与反向代理 |
| SQLite + 持久磁盘 | `DATABASE_URL=sqlite:////data/xinyu.db`，必须挂 Volume/Disk |
| ModelScope API Key | 对话、向量、图片模型；不配置则 AI 功能不可用 |
| Ollama | 可选，仅日记 AI 分析的本地降级路径 |
