/* Optional real-browser regression: node tests/browser_smoke.cjs */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");
const base = process.env.DRUGAGENT_WEB || "http://127.0.0.1:8077";
const artifacts = process.env.DRUGAGENT_SCREENSHOTS;
const events = [
  { type: "start", candidates: ["gefitinib"] },
  { type: "progress", stage: "literature" },
  {
    type: "stage",
    stage: "literature",
    text: "## 证据综述\nEGFR 相关知识 [PMID:123](https://pubmed.ncbi.nlm.nih.gov/123/)",
  },
  { type: "progress", stage: "molecules" },
  {
    type: "stage",
    stage: "molecules",
    text: "| 分子 | MW |\n|---|---|\n| gefitinib | 446.91 |",
    molecules: [{ name: "gefitinib", smiles: "CCO" }],
  },
  { type: "progress", stage: "optimization" },
  {
    type: "stage",
    stage: "optimization",
    text: "规则式优化完成",
    table_md: "**6 个类似物**",
    analogs: [
      {
        id: "A1",
        label: "芳环取代",
        smiles: "CCO",
        qed: 0.6,
        dqed: 0.1,
        sim: 0.8,
      },
    ],
  },
  { type: "progress", stage: "report" },
  {
    type: "stage",
    stage: "report",
    text: "## 综合评审\n计算结果需进一步验证。",
    refs: "PMID:123",
  },
  { type: "done", elapsed: 1.2, report_path: "report_browser.md" },
];
(async () => {
  const browser = await chromium.launch({
    executablePath:
      process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || "/usr/bin/chromium",
    headless: true,
    args: ["--no-sandbox"],
  });
  try {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1050 },
    });
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(base);
    await page.waitForFunction(() =>
      document
        .querySelector("#health-label")
        .textContent.includes("模型待配置"),
    );
    assert.equal(await page.locator("#go").isDisabled(), true);
    await page.locator("#search-button").click();
    await page.waitForSelector(".search-hit");
    assert.ok((await page.locator(".search-hit").count()) > 0);
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
      false,
    );
    await page.evaluate(() => window.scrollTo(0, 0));
    if (artifacts)
      await page.screenshot({
        path: `${artifacts}/workspace-desktop.png`,
        fullPage: true,
      });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
      false,
    );
    assert.ok(await page.locator("#go").isVisible());
    await page.evaluate(() => window.scrollTo(0, 0));
    if (artifacts)
      await page.screenshot({
        path: `${artifacts}/workspace-mobile.png`,
        fullPage: true,
      });
    // Only the browser's transport is replaced here; real SSE is separately tested in Python.
    await page.route("**/api/health", (route) =>
      route.fulfill({
        json: {
          analysis_configured: true,
          providers: [{ model: "test-provider", configured: true }],
        },
      }),
    );
    await page.route("**/api/run?*", (route) =>
      route.fulfill({
        contentType: "text/event-stream",
        body: events.map((e) => "data: " + JSON.stringify(e) + "\n\n").join(""),
      }),
    );
    await page.reload();
    await page.waitForFunction(() => !document.querySelector("#go").disabled);
    await page.locator("#go").click();
    await page.waitForFunction(() =>
      document.querySelector("#status").textContent.includes("分析完成"),
    );
    assert.equal(await page.locator(".pill.done").count(), 4);
    assert.equal(
      await page.locator("#download-report").getAttribute("href"),
      "/api/reports/report_browser.md",
    );
    assert.equal(await page.locator("#mol-grid img").count(), 1);
    assert.equal(await page.locator("#opt-grid img").count(), 1);
    assert.equal(await page.locator("#topic").isDisabled(), false);
    assert.equal(await page.locator("#go").isDisabled(), false);
    await page.waitForFunction(() =>
      [...document.querySelectorAll(".molecule-grid img")].every(
        (i) => i.complete && i.naturalWidth > 0,
      ),
    );
    const sanitized = await page.evaluate(async () => {
      const { renderMarkdown } = await import("/static/ui.js");
      const root = renderMarkdown(
        '<script>window.__unsafe=1</script><img src=x onerror="window.__unsafe=1"><a href="javascript:alert(1)" onclick="alert(1)">bad</a><svg onload="alert(1)"></svg>\n\n**safe text**',
      );
      document.body.append(root);
      return {
        script: root.querySelectorAll("script,img,svg,[onclick]").length,
        badLink: root.querySelector("a")?.getAttribute("href"),
        bold: root.querySelector("strong")?.textContent,
        executed: !!window.__unsafe,
      };
    });
    assert.equal(sanitized.script, 0);
    assert.equal(sanitized.badLink, null);
    assert.equal(sanitized.bold, "safe text");
    assert.equal(sanitized.executed, false);
    await page.unroute("**/api/run?*");
    await page.route("**/api/run?*", (route) =>
      route.fulfill({
        contentType: "text/event-stream",
        body: 'data: {"type":"progress","stage":"literature"}\n\ndata: {"type":"error","message":"测试：服务暂不可用"}\n\n',
      }),
    );
    await page.locator("#go").click();
    await page.waitForFunction(() =>
      document
        .querySelector("#status")
        .textContent.includes("测试：服务暂不可用"),
    );
    assert.equal(await page.locator("#p-lit").textContent(), "未完成");
    assert.equal(await page.locator("#go").isDisabled(), false);
    assert.equal(await page.locator("#download-report").isVisible(), false);
    assert.deepEqual(errors, []);
    console.log(
      "PASS browser: offline capabilities, desktop/mobile overflow, all stages, images, download, sanitization, error recovery",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
