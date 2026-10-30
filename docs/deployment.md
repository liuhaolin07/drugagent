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

如本机 8077 端口被占用，在 `.env` 中设置 `DRUGAGENT_PORT=8080` 后重新运行启动命令。启动脚本会显示实际端口。Linux/macOS 启动脚本已在本次交付中实测；Windows 批处理需要在 Windows 上验证。

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

## 本次验证范围

- Linux x86_64、Docker 28、Compose v2。
- 固定依赖安装、非 root 运行、健康检查。
- 实际 HTTP 首页、本地检索、RDKit 计算与 PNG 绘图。
- 报告下载、容器重启后的报告和缓存持久化。
- 真实在线模型分析仍需配置有效凭证和网络访问；Windows、ARM 与具体云平台部署未实测。
