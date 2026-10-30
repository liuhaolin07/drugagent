# 让别人开箱即用

推荐你统一部署一份服务，再把网址发给使用者。模型密钥只由部署者在服务端配置；使用者打开浏览器即可。需要交付给其他人独立运行时，使用下方 Docker 方案。

## 下载后独立运行

准备 Docker Desktop（Windows/macOS）或 Docker Engine + Compose v2.20+（Linux），解压发布包并进入 `drugagent` 目录。

1. 不使用模型密钥也可以启动网页，体验本地知识检索和分子绘图。
2. 需要完整分析时，把 `.env.example` 复制为 `.env`，在本机填写 `GLM_API_KEY` 或 `DEEPSEEK_API_KEY`。密钥不是安装包的一部分。
3. Windows 双击 `start.bat`；macOS/Linux 执行 `sh scripts/start.sh`。也可以直接运行：

   ```bash
   docker compose up -d --build --wait --wait-timeout 120
   ```

默认打开 `http://localhost:8077`。首次会下载基础镜像和固定版本依赖；无需自行安装 Python、RDKit、Node.js 或数据库。后续启动会复用已构建镜像。

如本机 8077 端口被占用，在 `.env` 中设置 `DRUGAGENT_PORT=8080` 后重新运行启动命令。启动脚本会显示实际端口。Shell 启动脚本已在 Linux 上实测；Windows 的 `start.bat` 已根据本地 agent 的验收报告确认通过。macOS 尚未实测。

## 由你部署，使用者打开网址

在有公网地址或内网访问地址的 Linux 服务器上安装 Docker + Compose，将发布包解压后按上面的命令启动。在服务器的 `.env` 中配置模型密钥，不把密钥发给使用者。

两种访问方式：

- **小组内网使用**：`.env` 增加 `DRUGAGENT_BIND_ADDRESS=0.0.0.0`，服务启动后，组员访问 `http://服务器地址:8077`。确认服务器允许组员所在网络访问该端口。
- **域名访问**：保留默认回环地址绑定，在服务器的 Nginx/Caddy 反向代理到 `127.0.0.1:8077`，配置域名与 HTTPS。使用者随后只需访问域名。

Nginx 示例（放入已经配置 HTTPS 的站点中）：

```nginx
location / {
    proxy_pass http://127.0.0.1:8077;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 600s;
}
```

分析进度使用 SSE，代理必须关闭响应缓冲，读取超时应覆盖一次完整分析。当前平台是**共享研究工作区**：访问者能看到同一份历史报告。开放互联网多用户服务前，需要增加登录、个人报告隔离和调用配额；小组访问可先在现有网关上控制成员访问。

部署在线流程的服务器需能访问：

- GLM：`open.bigmodel.cn`，或 DeepSeek：`api.deepseek.com`。
- 分子与论文：`pubchem.ncbi.nlm.nih.gov`、`eutils.ncbi.nlm.nih.gov`。
- 构建期间：Docker Hub、Debian 软件仓库、PyPI。

本文提供可移植部署步骤；没有自动创建服务器、注册域名或发布公网服务。

## 使用云托管容器平台

将仓库发布到你自己的 GitHub 后，选择支持 Dockerfile 的容器托管服务：

- 构建文件：项目根目录 `Dockerfile`。
- 容器监听：`0.0.0.0:8077`，健康检查：`/api/health`。
- 运行环境：在平台秘密变量中设置模型密钥。
- 持久卷：挂载到 `/app/storage`，容器内运行用户 UID/GID 为 `10001:10001`。
- 启动：使用镜像自带命令 `python web.py`。

如果平台要求使用分配的端口，把平台端口值设置到 `DRUGAGENT_PORT`，并同步容器的流量路由配置。平台自动提供的 `PORT` 不会被应用隐式读取。

本项目没有绑定特定云厂商账户；镜像在本地验证通过不代表已发布公网网址。

## 数据、更新与排错

报告与可重建缓存存放在 `drugagent-storage` 命名卷中，重建/重启容器后保留；内置语料和候选数据随镜像更新，避免旧缓存卷覆盖新语料。

```bash
# 查看运行与健康状态
docker compose ps

# 检查服务日志，不输出 .env 或容器环境变量
docker compose logs --tail 100 drugagent

# 环境自检，不发起外部请求
docker compose exec -T drugagent python check_env.py

# 显式验证在线源和模型，会调用模型 API
docker compose exec -T drugagent python check_env.py --online

# 修改代码或 .env 后更新服务
docker compose up -d --build --wait --wait-timeout 120

# 停止服务并保留报告卷
docker compose down
```

`docker compose down --volumes` 会删除命名卷中的报告和缓存，日常停止不要加 `--volumes`。

`/api/health` 成功说明服务可响应，不等于模型和在线数据源已可访问。配置密钥后应完成一次真实分析，以最终 SSE `done` 和新生成的报告作为验收依据。

## 生成交付包

```bash
python3 scripts/package_release.py
```

默认输出 `dist/DrugAgent-v0.5.0.zip`，包含当前工作目录中的发布代码与部署文件。脚本使用明确的文件清单；不会打包 `.env`、本机虚拟环境、缓存、报告、Git 数据或浏览器截图。交付包不是容器离线镜像，首次运行仍需联网构建。

`requirements.lock` 固定本次验证的 Python 包版本与 SHA-256 哈希；Docker 安装时强制校验。更新依赖时应重新生成锁定文件并验证，再打包分发。

## 验证范围

- Linux x86_64、Docker 28、Compose v2。
- 固定依赖安装、非 root 运行、健康检查。
- 实际 HTTP 首页、本地检索、RDKit 计算与 PNG 绘图。
- 报告下载、容器重启后的报告和缓存持久化。
- Windows 本机 Docker：根据用户提供的本地 agent 报告，`start.bat`、基础功能、真实在线分析和重启持久化已通过；详见下方验收记录。
- 云端执行过 19 项后端测试；本机 agent 未修改代码，因此没有在 Windows 宿主机重复运行该套测试。
- macOS、ARM、具体云平台和公网域名部署尚未实测。


## 验收记录

### 2026-10-30：Windows Docker 本机验收

**结果来源：用户提供的本地 agent 完成报告。本记录汇总本机验证结果，未在云端重新调用用户的模型服务。**

验收对象：`codex/platform-deployment-handoff` 分支，运行提交 `fe41c77074770241b5562587c6c1353bd67e4e1d`。本机工作区干净，未改动代码。

| 项目 | 本机报告结果 |
| --- | --- |
| 运行环境 | Windows 本机 Docker Compose，Python 3.12 / RDKit 2026.09.1 / OpenAI 3.41.0；具体 Windows 与 Docker 引擎版本未提供 |
| 启动 | `docker compose up -d --build --wait --wait-timeout 180` 与 `start.bat` 均通过；进程以 UID 10001 运行 |
| 访问范围 | `127.0.0.1:8077`，仅本机回环访问 |
| 基础功能 | 健康检查、首页与静态资源、4 条本地 EGFR 知识、260×200 PNG、报告列表均通过 |
| 无密钥行为 | 单独的空密钥容器显示模型待配置，分析返回 `missing_provider` |
| 浏览器 | 1440 / 390 宽度布局、结构图、Markdown 清洗与错误恢复通过；`browser_smoke.cjs` 全项通过 |
| 在线自检 | PubChem + RDKit、PubMed、模型请求均通过；GLM 与 DeepSeek 均有配置，报告未逐个验证两个 provider 的独立调用 |
| 完整分析 | 4 次真实运行（2 次接口、2 次网页），均完成四个阶段并以 `done` 结束；耗时 73–108 秒 |
| 文献来源 | 实际取得 PMID 40996745、40675056、38636443、39073550；文献阶段 `warnings` 为空 |
| 分子计算 | gefitinib：MW 446.91 / logP 4.28 / TPSA 68.74 / QED 0.518；6 个候选逐项判定 Lipinski |
| 分子优化 | 生成 55 个类似物、48 个通过筛选、Top 6；网页 6 张候选图与 6 张类似物图均真实解码 |
| 持久化 | 重启后约 4 秒恢复健康，报告数量与最新报告 SHA-256 一致，下载正常 |
| 密钥处理 | 本机配置未提交到 Git，未在聊天或日志中输出；本记录不包含密钥 |

已知偏差：首次在线自检出现一次 `SSLError`，随后连续两次自检通过，根因未确认；一次终端 GBK 编码导致的中文主题乱码已改为 UTF-8 请求并清理对应测试报告；`/favicon.ico` 返回 404，未影响功能。

验收结束时保留 3 份正常中文报告，服务继续在本机运行。公网访问、ARM、macOS 与特定云平台部署不属于这次本机验收范围。
