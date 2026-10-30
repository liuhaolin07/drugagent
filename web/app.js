import { renderMarkdown, moleculeCard } from "./ui.js";

const $ = (id) => document.getElementById(id);
const stages = ["literature", "molecules", "optimization", "report"];
const short = {
  literature: "lit",
  molecules: "mol",
  optimization: "opt",
  report: "rep",
};
const stageNames = {
  literature: "文献检索",
  molecules: "分子分析",
  optimization: "分子优化",
  report: "综合评审",
};
const state = {
  source: null,
  timer: null,
  configured: false,
  running: false,
  completed: 0,
  active: null,
};
const initial = Object.fromEntries(
  stages.map((key) => [key, $(`c-${short[key]}`).innerHTML]),
);

function setStage(stage, status) {
  if (!stages.includes(stage)) return;
  const pill = $(`p-${short[stage]}`);
  pill.className = `pill ${{ running: "run", done: "done", error: "error" }[status] || ""}`;
  pill.textContent = {
    running: "进行中",
    done: "已完成",
    error: "未完成",
    waiting: "等待",
  }[status];
  const step = document.querySelector(`[data-stage="${stage}"]`);
  step.className = `step ${status}`;
  step.querySelector("i").textContent = {
    running: "进行中",
    done: "完成",
    error: "中断",
    waiting: "待开始",
  }[status];
}
function finish(message, failed = false) {
  state.source?.close();
  state.source = null;
  clearInterval(state.timer);
  state.timer = null;
  state.running = false;
  $("go").disabled = !state.configured;
  $("go").innerHTML = '开始分析 <span aria-hidden="true">↗</span>';
  $("topic").disabled = false;
  $("status").textContent = message;
  if (failed && state.active) setStage(state.active, "error");
  state.active = null;
}
function begin(topic) {
  if (state.running || !state.configured) return;
  state.running = true;
  state.completed = 0;
  state.active = null;
  $("go").disabled = true;
  $("go").textContent = "分析进行中…";
  $("topic").disabled = true;
  $("download-report").hidden = true;
  $("progress-bar").style.width = "0%";
  for (const stage of stages) {
    setStage(stage, "waiting");
    $(`c-${short[stage]}`).innerHTML = initial[stage];
  }
  $("mol-grid").replaceChildren();
  $("opt-grid").replaceChildren();
  const start = Date.now();
  $("elapsed").textContent = "00:00";
  $("status").textContent = "正在创建分析任务";
  state.timer = setInterval(() => {
    const elapsed = Math.floor((Date.now() - start) / 1000);
    $("elapsed").textContent =
      `${String(Math.floor(elapsed / 60)).padStart(2, "0")}:${String(elapsed % 60).padStart(2, "0")}`;
  }, 500);
  try {
    state.source = new EventSource(
      `/api/run?${new URLSearchParams({ topic })}`,
    );
  } catch {
    finish("无法连接分析服务，请重试。", true);
    return;
  }
  state.source.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "start") $("status").textContent = "任务已启动";
      else if (data.type === "progress" && stages.includes(data.stage)) {
        state.active = data.stage;
        setStage(data.stage, "running");
        $("status").textContent = `正在${stageNames[data.stage]}…`;
      } else if (data.type === "stage" && stages.includes(data.stage)) {
        setStage(data.stage, "done");
        const markdown = [data.text, data.table_md, data.refs]
          .filter(Boolean)
          .join("\n\n");
        $(`c-${short[data.stage]}`).replaceChildren(renderMarkdown(markdown));
        for (const warning of data.warnings || []) {
          const notice = document.createElement("p");
          notice.className = "notice";
          notice.textContent = warning;
          $(`c-${short[data.stage]}`).prepend(notice);
        }
        state.completed = stages.indexOf(data.stage) + 1;
        $("progress-bar").style.width = `${state.completed * 25}%`;
        if (data.stage === "molecules") {
          $("mol-grid").replaceChildren(
            ...(data.molecules || [])
              .filter((m) => !m.error && m.smiles)
              .map((m) => moleculeCard(m)),
          );
        }
        if (data.stage === "optimization") {
          $("opt-grid").replaceChildren(
            ...(data.analogs || []).map((a) =>
              moleculeCard({
                name: a.id,
                smiles: a.smiles,
                label: `${a.id} · ${a.label} / QED ${a.qed} / Δ${a.dqed > 0 ? "+" : ""}${a.dqed} / 相似度 ${a.sim}`,
              }),
            ),
          );
        }
      } else if (data.type === "done") {
        finish(`分析完成 · 用时 ${data.elapsed}s`);
        if (data.report_path) {
          $("download-report").href =
            `/api/reports/${encodeURIComponent(data.report_path)}`;
          $("download-report").hidden = false;
        }
        loadReports();
      } else if (data.type === "error")
        finish(data.message || "分析未能完成，请重试。", true);
    } catch {
      finish("分析数据格式异常，请重试。", true);
    }
  };
  state.source.onerror = () =>
    finish("连接已中断。已收到的结果保留，请重试。", true);
}

async function request(url) {
  const response = await fetch(url, { signal: AbortSignal.timeout(20000) });
  if (!response.ok) throw new Error("服务请求失败");
  return response.json();
}
async function loadHealth() {
  try {
    const health = await request("/api/health");
    state.configured = health.analysis_configured;
    $("health-label").textContent = state.configured
      ? "分析服务已配置"
      : "本地功能可用 · 模型待配置";
    $("health-dot").className =
      `status-dot ${state.configured ? "ready" : "warning"}`;
    $("provider-label").textContent =
      health.providers
        .filter((p) => p.configured)
        .map((p) => p.model)
        .join(" / ") || "待配置";
    $("go").disabled = !state.configured;
    if (!state.configured) {
      $("config-notice").textContent =
        "完整分析需要模型密钥。请配置 GLM_API_KEY 或 DEEPSEEK_API_KEY 并重启服务；本地知识检索可直接使用。";
      $("config-notice").hidden = false;
    }
  } catch {
    $("health-label").textContent = "服务状态检测失败";
    $("health-dot").className = "status-dot error";
    $("config-notice").textContent =
      "无法读取服务状态，请检查后端是否正常运行并刷新页面。";
    $("config-notice").hidden = false;
  }
}
async function loadReports() {
  const list = $("report-list");
  try {
    const data = await request("/api/reports");
    list.replaceChildren();
    if (!data.reports.length) {
      list.textContent = "还没有报告，完成一次分析后会显示在这里。";
      return;
    }
    for (const report of data.reports) {
      const row = document.createElement("div");
      row.className = "report-row";
      const info = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = report.title;
      const time = document.createElement("time");
      time.dateTime = report.created_at;
      time.textContent = new Date(report.created_at).toLocaleString("zh-CN");
      info.append(title, time);
      const link = document.createElement("a");
      link.href = `/api/reports/${encodeURIComponent(report.name)}`;
      link.textContent = "下载 ↓";
      row.append(info, link);
      list.append(row);
    }
  } catch {
    list.textContent = "报告列表读取失败，请点击刷新重试。";
  }
}
$("analysis-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const topic = $("topic").value.trim();
  if (topic) begin(topic);
});
for (const button of document.querySelectorAll("[data-topic]"))
  button.addEventListener("click", () => {
    if (!state.running) {
      $("topic").value = button.dataset.topic;
      $("topic").focus();
    }
  });
$("refresh-history").addEventListener("click", loadReports);
$("search-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = $("search-query").value.trim();
  if (!query) return;
  const button = $("search-button");
  const target = $("search-results");
  button.disabled = true;
  target.textContent = "检索中…";
  try {
    const data = await request(`/api/search?${new URLSearchParams({ query })}`);
    target.replaceChildren();
    if (!data.results.length) target.textContent = "没有找到相关知识。";
    for (const hit of data.results) {
      const article = document.createElement("article");
      article.className = "search-hit";
      const title = document.createElement("h3");
      title.textContent = hit.title;
      const text = document.createElement("p");
      text.textContent = hit.text;
      const source = document.createElement("small");
      source.textContent = hit.source;
      article.append(title, text, source);
      target.append(article);
    }
  } catch {
    target.textContent = "检索失败，请检查服务状态并重试。";
  } finally {
    button.disabled = false;
  }
});
window.addEventListener("pagehide", () => {
  state.source?.close();
  clearInterval(state.timer);
});
loadHealth();
loadReports();
