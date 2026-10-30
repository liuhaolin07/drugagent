# 开发与 API 参考

[返回仓库首页](../README.md) · [部署说明](deployment.md)

以下命令均从仓库根目录执行。

## 启动

需要 Python 3.12（已验证），无需数据库、GPU 或前端构建工具。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements.lock
python check_env.py
python web.py
```

默认监听 `127.0.0.1:8077`。Windows 使用 `.venv\Scripts\activate` 激活，或直接运行 `.venv\Scripts\python.exe web.py`；已有批处理入口继续可用。

完整分析需要至少一个模型服务密钥，可在平台环境设置中注入 `GLM_API_KEY` / `DEEPSEEK_API_KEY`，也可将 `.env.example` 复制为项目根目录的 `.env` 并在本机填写。**不要提交或在日志中输出密钥。** `.env` 已被 Git 忽略；环境变量优先于文件配置。配置变更后需要重启服务。

| 变量 | 默认值 / 用途 |
| --- | --- |
| `GLM_API_KEY` | 智谱模型与 embedding-3；默认优先使用 |
| `DEEPSEEK_API_KEY` | DeepSeek 对话回退；不会提供 GLM embedding |
| `DRUGAGENT_MODEL` | `glm-4-flash`，GLM 对话模型 |
| `DRUGAGENT_ENV_FILE` | 项目根目录 `.env`；可指定其他配置文件 |
| `DRUGAGENT_HOST` | `127.0.0.1` |
| `DRUGAGENT_PORT` | `8077` |
| `DRUGAGENT_REPORTS_DIR` | `reports`；相对路径基于项目根目录 |
| `DRUGAGENT_CACHE_DIR` | `data`；Docker 中独立缓存目录位于持久卷内 |

无密钥时，网页会说明配置状态并禁用完整分析，本地 BM25 知识检索和按 SMILES 绘图仍可使用。语义检索不可用时自动回退 BM25；不会将缺少模型凭证的分析标记为完成。

```bash
# CLI 使用与网页相同的流程、存档格式和错误处理
python run.py "EGFR 抑制剂"

# 显式验证模型及在线数据源（会调用模型 API）
python check_env.py --online
```

在线流程需要 HTTPS 访问 `open.bigmodel.cn`（GLM）、`api.deepseek.com`（选择 DeepSeek 时）、`pubchem.ncbi.nlm.nih.gov` 和 `eutils.ncbi.nlm.nih.gov`。状态接口中的“已配置”仅表示存在凭证，不表示远程服务已验证可访问。

## 架构

```text
web.py / run.py
  └─ drugagent.service.AnalysisService
       ├─ agents.Team
       │    ├─ 文献：本地检索 + PubMed → 模型解读
       │    ├─ 分子：PubChem + RDKit → 模型解读
       │    ├─ 优化：规则枚举 + Lipinski/相似度筛选 → 模型解读
       │    └─ 评审：模型评语 + 代码生成的原始性质表/优化表
       └─ drugagent.reports.ReportStore → 原子写入、列表、下载
```

- `drugagent/api.py`：应用工厂 `create_app()`、HTTP 校验、SSE 适配和报告接口；保留 `web:app` 部署入口。
- `drugagent/service.py`：统一生命周期和稳定错误码；四个阶段全部完成后才存档。
- `drugagent/reports.py`：共享报告格式、带唯一标识的文件名和报告路径校验。
- `drugagent/images.py`：最多 256 项的分子图片缓存。
- `config.py` / `llm.py`：可移植配置、延迟初始化、多 provider 回退；公开状态只含名称与配置状态。
- `tools/`：保留分子计算与生成逻辑；JSON 缓存采用原子替换，线程内共享缓存访问有锁保护。
- `web/index.html` / `styles.css` / `app.js` / `ui.js`：结构、样式、交互和白名单 Markdown 渲染分离；资源全部本地加载。

分子数据先由确定性工具计算，再交给模型解读；表格由代码生成并附加到报告。PubMed 不可用时会明确显示来源警告；所有候选数据均失败时，流程中止且不发布报告。模型评语仍需研究者核对，代码表格不等同于模型文字准确性保证。

## API

| 方法与路径 | 用途 |
| --- | --- |
| `GET /api/health` | 服务状态、模型配置及本地能力；不包含凭证 |
| `GET /api/candidates` | 内置候选集与适用范围 |
| `GET /api/search?query=EGFR&top=4` | 本地知识检索，最多 20 条 |
| `GET /api/run?topic=EGFR` | SSE 分析流；主题须为 1–200 字符的非空白文本 |
| `GET /api/molimg?smiles=CCO` | PNG 结构图；也兼容 `name=gefitinib` |
| `GET /api/reports` | 最近 50 份报告 |
| `GET /api/reports/{name}` | 下载已归档的 Markdown 报告 |

SSE 成功流程为 `start → progress → stage → … → done`，异常以 `error` 结束。`stage` 保留原来的 `stage / status / text` 字段，新增结构化 `molecules`、`table_md`、`warnings` 等。客户端应分别渲染 `text`、`table_md` 与 `refs`。仅收到 HTTP 200 不代表分析成功；必须检查最终 `done`。缺少密钥会直接返回 `error(code=missing_provider)`，不发起外部请求。

报告不依赖进程内任务列表，重启后仍可下载；执行中的分析、SSE 连接和缓存中的图片不会恢复。本版面向本机/受控研究环境，未实现用户账户、租户隔离、持久任务队列或跨进程缓存写锁。多 worker 部署前需引入共享存储和任务服务。

## 验证

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

回归测试覆盖缺少密钥的重复请求与 BM25 回退、provider 切换、真实 RDKit 流程、阶段顺序、来源失败、CLI 退出码、SSE、并发存档、下载及路径校验。测试仅替换远程模型与在线数据请求，不代表外部 API 已验证。

可选浏览器检查使用 Node.js + Playwright 和已安装的 Chromium；在未配置密钥的本地服务上运行：

```bash
# Playwright 需要在 Node 模块搜索路径中；可安装到独立的开发工具目录
npm install --prefix /tmp/drugagent-browser playwright
NODE_PATH=/tmp/drugagent-browser/node_modules \
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium \
node tests/browser_smoke.cjs
```

通过 `DRUGAGENT_WEB` 可指定测试地址。设置 `DRUGAGENT_SCREENSHOTS` 为已有目录可保存截图。浏览器检查覆盖桌面/手机布局、本地检索、前端阶段处理、失败恢复和 Markdown 渲染；完整分析的浏览器响应使用测试事件，后端真实流程另由 Python 测试验证。原 `check_webui.py` 是 v0.4 的 Windows Edge 在线演示工具，不作为本版的回归入口。

内置语料位于 `data/corpus.json`；PubMed 与向量缓存默认分别写入 `data/paper_cache.json` 和 `data/embed_cache.json`，可通过 `DRUGAGENT_CACHE_DIR` 更换目录。报告保存在 `reports/`，这些运行产物均被 Git 忽略。旧版示例报告见 [example_report_EGFR.md](example_report_EGFR.md)。

仅供学习与研究，不构成医疗建议。
