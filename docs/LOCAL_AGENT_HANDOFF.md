# 本地 Agent 部署交接

## 给本地 Agent 的任务

在用户本机部署 DrugAgent v0.5，默认优先使用 Docker Compose。先完成无需模型密钥的本地功能验收，再复用本机已有的模型凭证验证真实在线分析。不要把健康检查成功当作完整分析成功。除非用户明确要求服务器或域名部署，否则先完成本机运行。

本次交付分支：`codex/platform-deployment-handoff`。

```text
请部署 https://github.com/liuhaolin07/drugagent 的 codex/platform-deployment-handoff 分支。
先读 docs/LOCAL_AGENT_HANDOFF.md 和 docs/deployment.md，按交接文档完成本机启动、
基础功能与真实分析验收，遇到环境问题继续诊断解决，不要只给出操作计划。
已有目录请保留修改；密钥只使用本机环境变量或未跟踪的 .env，不要在聊天或日志中输出。
```

## 取得完整代码

首次部署：

```bash
git clone --branch codex/platform-deployment-handoff --single-branch https://github.com/liuhaolin07/drugagent.git
cd drugagent
```

如果已有同名目录，先检查 `git status`，保存已有修改，使用 `git fetch origin` 获取远端分支；不要执行破坏性 reset 或覆盖 `.env`。有本地改动时可另选一个空目录 clone。

代码与资源全部在 Git 中，不需要下载云端文件。主要入口：

| 资源 | 作用 |
| --- | --- |
| `Dockerfile` | Python 3.12、RDKit 系统库、非 root 用户和构建期绘图检查 |
| `compose.yaml` | 启动端口、模型变量、健康检查、自动重启和持久卷 |
| `requirements.lock` | 已验证的依赖版本与 SHA-256 哈希 |
| `.env.example` | 本机/服务端配置模板，不含密钥 |
| `start.bat` / `scripts/start.sh` | Windows / macOS、Linux 启动入口 |
| `docs/deployment.md` | 服务器、域名、SSE 代理、持久化与排错 |
| `tests/test_platform.py` | 19 项后端回归测试 |
| `tests/browser_smoke.cjs` | 可选 Chromium/Playwright 页面回归 |
| `scripts/package_release.py` | 可选源码交付包生成，不包含密钥与运行数据 |

## 1. 检查本机前提

- Docker Desktop 已安装并运行，或 Linux Docker Engine + Compose v2.20+ 可用。
- 执行 `docker info` 和 `docker compose version`；Docker 不可用时先解决安装、daemon、WSL2 或 socket 权限。
- 检查 8077 端口是否可用；被占用时在 `.env` 里设 `DRUGAGENT_PORT=8080`，不要终止无关服务。
- 首次构建需要访问 Docker Hub、Debian 仓库、PyPI。保留用户已有代理与 CA 信任，保持 TLS、软件包签名和哈希校验。
- 默认不用在宿主机安装 Python、Node、数据库或 CUDA。

云端专用的 `/workspace`、`/etc/codex` 和代理 CA 路径不属于本机部署前提，不能原样写入本机配置。如果本机企业代理需要自定义 CA，用 Dockerfile 支持的 `proxy_ca` build secret 提供合并的可信证书链；不要修改锁文件哈希或关闭验证。

## 2. 准备配置，保护已有值

优先检查本机现有环境变量中 `GLM_API_KEY` / `DEEPSEEK_API_KEY` 的名称与是否设置。环境中已有有效值时，Compose 会直接使用，不需要重复填写。

如果需要 `.env`，只在它不存在时复制：

Linux/macOS：

```bash
[ -f .env ] || cp .env.example .env
```

Windows PowerShell：

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

由用户在本地编辑器或秘密变量管理工具中配置至少一个模型服务：

- `GLM_API_KEY`：默认使用 GLM 对话模型与 embedding-3。
- `DEEPSEEK_API_KEY`：可作为对话模型替代或回退；未配置 GLM 时，本地检索用 BM25。

不要要求用户把密钥贴到聊天中，不要输出 `.env`、完整进程环境或 `docker compose config` 的展开结果。无密钥仍可先完成网页、本地知识检索及 SMILES 绘图验收，但完整分析应如实标记为待验证。

模型默认是 `glm-4-flash`；如果本机凭证对应的账户已不支持该模型，核对服务商当前可用模型，并使用 `DRUGAGENT_MODEL` 配置受支持的 GLM 模型。不要凭空猜测模型已可访问。

## 3. 启动

通用命令，Windows PowerShell 也可执行：

```bash
docker compose up -d --build --wait --wait-timeout 120
docker compose ps
```

或者 Windows 双击 `start.bat`，macOS/Linux 执行 `sh scripts/start.sh`。

默认访问 `http://localhost:8077`；设置了自定义端口则使用实际端口。`docker compose port drugagent 8077` 可读取映射端口。默认只监听本机回环地址，不会自动开放公网。

首次构建可能耗时数分钟，`--wait-timeout` 是服务启动后的健康等待时间，不是整个镜像构建超时。启动失败时读取日志定位原因，再依据诊断修复，不要重复运行相同失败命令。

```bash
docker compose logs --tail 100 drugagent
docker compose exec -T drugagent python check_env.py
docker compose exec -T drugagent python -m drugagent.healthcheck
```

## 4. 基础功能验收

必须实际验证，不要只检查 PID 或端口：

1. `/api/health` 返回 `status=ok`、`version=0.5.0`；模型 `configured` 仅代表有配置。
2. 首页可打开，静态资源正常，手机/窄屏布局可用。
3. 在网页的“本地知识库”检索 `EGFR`，确认返回真实条目。
4. 打开 `/api/molimg?smiles=CCO`，确认得到可解码的 260×200 PNG。
5. 打开历史报告区域，确认列表可读；空列表是正常初始状态。
6. 没有模型凭证时，网页应明确提示模型待配置，完整分析应返回 `missing_provider`，不能伪造成功。

Linux/macOS 可用 curl；Windows PowerShell 可用 `Invoke-RestMethod`，访问图像时可用浏览器。验证时不要把模型密钥放进 URL。

## 5. 真实在线分析验收

先确认部署机器能访问实际选择的模型服务，以及 PubChem、PubMed：

- `open.bigmodel.cn` 或 `api.deepseek.com`
- `pubchem.ncbi.nlm.nih.gov`
- `eutils.ncbi.nlm.nih.gov`

配置凭证后重新执行启动命令以更新容器环境，再运行：

```bash
docker compose exec -T drugagent python check_env.py --online
```

此命令会调用模型 API。成功后通过网页执行一次 `EGFR 抑制剂` 完整分析。也可使用 SSE：

```bash
curl --no-buffer --max-time 600 --get --data-urlencode "topic=EGFR 抑制剂" http://localhost:8077/api/run
```

改了端口时同步调整请求。验收条件：

- 依次完成 `literature`、`molecules`、`optimization`、`report`。
- 最后一条事件是 `done`，不是 `error`；HTTP 200 本身不够。
- 有真实的分子性质与类似物结构图；属性和表格由 RDKit/代码计算。
- 有新报告，网页可下载对应 Markdown。
- 论文服务若不可用，会显示来源警告；要宣称在线论文验证通过，必须实际拿到 PubMed 论文，不能把降级运行当作论文源成功。
- 执行 `docker compose restart drugagent` 并等到健康后，确认刚才的报告仍可下载。

当前是内置 EGFR 演示候选集，输入其他靶点不会自动换成该靶点的候选分子。当前是共享研究工作区，不提供个人账户或报告隔离。

## 6. 需要修改代码时的回归

如果本地 agent 为修复环境或平台兼容性而改动代码，再建立宿主机开发环境：

```bash
python3 -m venv .venv
# Linux/macOS 使用 .venv/bin/python；Windows 使用 .venv/Scripts/python.exe
.venv/bin/python -m pip install --require-hashes -r requirements.lock
.venv/bin/python -m unittest discover -s tests -v
```

某些较旧的 FastAPI/Starlette 版本需要 `requirements-dev.txt` 中的 httpx；本次锁定版本已经可以运行测试。不要为了让检查通过而替换真实计算或禁用断言。Docker 流程验证通过后，没有改代码时不要求宿主机重复安装依赖。

## 7. 停止、更新与交付反馈

```bash
# 停止，保留报告与缓存
docker compose down

# 修改配置或代码后更新
docker compose up -d --build --wait --wait-timeout 120
```

日常停止不要加 `--volumes`，该选项会删除报告及缓存。不要在有未保存修改的目录中直接 pull、reset 或切换分支。

完成后向用户报告：操作系统与架构、实际运行 commit、启动命令、访问地址、基础验收结果、模型/PubMed/PubChem 是否真实验证、报告与重启持久化是否通过。明确列出失败或未执行项及其原因，不输出秘密值。

## 云端已完成的验证基线

- Linux x86_64，Docker 28 / Compose v2。
- 发布包在全新目录解压后运行一键启动脚本，通过健康检查。
- 非 root UID 10001 运行，镜像未包含本机 `.env` 或虚拟环境。
- 真实 RDKit：示例 gefitinib 母体生成 55 个类似物、48 个通过筛选，输出 Top 6。
- 真实容器 HTTP：页面、本地 EGFR 检索、PNG 绘图、报告下载。
- 删除容器后重新创建，报告与缓存仍保留。
- 19 项后端测试通过；浏览器布局、渲染与交互检查通过。
- 云端未配置模型密钥，完整在线分析仍需本地 agent 使用本机凭证验证。
- Windows 批处理、ARM、具体云厂商与公网域名部署尚未实测。
