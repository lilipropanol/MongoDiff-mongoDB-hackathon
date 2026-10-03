import { chromium } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import assert from "node:assert/strict";
import vm from "node:vm";
import { readFile } from "node:fs/promises";

const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome",
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
});
await context.addInitScript(() => {
  localStorage.setItem("schema-guard-theme", "dark");
});
const page = await context.newPage();
const errors = [],
  consoleErrors = [],
  plans = [];
page.on("pageerror", (error) => errors.push(error.message));
page.on("console", (message) => {
  if (message.type() !== "error") return;
  if (
    message.location().url.endsWith("/api/analyze") &&
    message.text().includes("409 (Conflict)")
  )
    return;
  consoleErrors.push(message.text());
});
page.on("response", async (response) => {
  if (response.url().endsWith("/plan") && response.ok())
    plans.push(await response.json());
});
async function settle() {
  await page.evaluate(async () => {
    while (true) {
      const animations = document
        .getAnimations()
        .filter(
          (animation) =>
            animation.effect?.getComputedTiming().iterations !== Infinity &&
            animation.playState !== "finished" &&
            animation.playState !== "idle",
        );
      if (!animations.length) return;
      // A theme change can replace a transition; cancellation is normal.
      await Promise.all(
        animations.map((animation) => animation.finished.catch(() => {})),
      );
    }
  });
}
async function accessible(label) {
  await settle();
  const result = await new AxeBuilder({ page }).analyze();
  assert.deepEqual(
    result.violations.map((v) => ({
      id: v.id,
      nodes: v.nodes.map((n) => ({ html: n.html, summary: n.failureSummary })),
    })),
    [],
    label,
  );
}
async function openDetails(name) {
  await page.getByRole("button", { name, exact: true }).click();
  await page.getByRole("dialog").waitFor();
}
async function checkScript() {
  await page
    .getByRole("button", { name: "Apply Fix & Rescan", exact: true })
    .waitFor();
  await page.waitForFunction(
    () => !document.querySelector(".plan-actions button")?.disabled,
  );
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page
      .getByRole("button", {
        name: "Download MongoDiff_fix.js",
        exact: true,
      })
      .click(),
  ]);
  const script = await readFile(await download.path(), "utf8");
  const calls = [];
  let database, collection;
  vm.runInNewContext(script, {
    db: {
      getSiblingDB(name) {
        database = name;
        return {
          getCollection(name) {
            collection = name;
            return {
              updateMany(filter, update) {
                calls.push({ filter, update });
              },
            };
          },
        };
      },
    },
  });
  assert.equal(database, "schema_guard_demo");
  assert.equal(collection, "movies");
  const plan = plans.at(-1);
  assert.ok(plan?.operations.length);
  assert.deepEqual(
    JSON.parse(JSON.stringify(calls)),
    plan.operations.map((op) => ({ filter: op.filter, update: op.update })),
    "displayed script must match the reviewed API plan",
  );
}
try {
  await page.goto(
    process.argv[2] || process.env.GUARD_UI_URL || "http://127.0.0.1:8000",
    { waitUntil: "networkidle" },
  );
  await page.getByTestId("failure-count").waitFor();
  await page.evaluate(() => document.fonts.ready);
  await settle();
  assert.equal(
    await page.getByTestId("failure-count").textContent(),
    "7 of 12",
  );
  assert.equal(
    await page
      .getByRole("tab", { name: /MongoDiff/ })
      .getAttribute("aria-selected"),
    "true",
  );
  assert.equal(
    await page
      .getByRole("tab", { name: "Documents", exact: true })
      .isDisabled(),
    true,
  );
  assert.equal(await page.locator(".cause-table tbody tr").count(), 3);
  assert.deepEqual(
    await page.locator(".cause-table .count-column strong").allTextContents(),
    ["4", "2", "2"],
  );
  assert.equal(await page.locator("textarea").count(), 0);
  assert.equal(
    await page
      .getByRole("textbox", { name: "Filter issues", exact: true })
      .count(),
    0,
  );
  const text = await page.locator("body").innerText();
  for (const removed of [
    "Git / PR linkage",
    "APPLICATION MODEL",
    "BREAKING DOCUMENTS",
    "COLLECTION VALIDATOR",
    "Triage action",
    "Model rule",
    "pre-existing drift*",
    "Reason counts can overlap",
    "Analysis complete. No data was changed.",
    "Fixture adapter · Run",
  ])
    assert.equal(text.includes(removed), false, `${removed} removed`);
  await page
    .getByText(
      "Scan complete for collection movies against proposed model Movie.",
    )
    .waitFor();
  await page.getByText("MongoDB Atlas MongoDiff · v1.0.0").waitFor();
  await checkScript();
  await page.screenshot({
    path: "/tmp/schema-guard-atlas-light.png",
    fullPage: true,
  });
  assert.equal(await page.locator("html").getAttribute("data-theme"), "light");
  await accessible("default light MongoDiff");
  await page
    .getByRole("textbox", { name: "Filter collections", exact: true })
    .fill("no-such-collection");
  await page.getByText("No matching collections.").waitFor();
  await page
    .getByRole("textbox", { name: "Filter collections", exact: true })
    .fill("");
  await openDetails("Details for runtime: Missing or empty value");
  await page.getByText("Missing from document", { exact: true }).waitFor();
  assert.match(await page.getByRole("dialog").innerText(), /null/);
  await accessible("grouped missing/null inspection");
  await page.keyboard.press("Escape");
  await openDetails("Details for rated: Missing or invalid value");
  assert.match(await page.getByRole("dialog").innerText(), /NR/);
  assert.match(await page.getByRole("dialog").innerText(), /PG13/);
  assert.equal(
    await page.getByRole("dialog").locator(".document-card").count(),
    4,
  );
  assert.equal(
    (await page.getByRole("dialog").innerText()).includes("Example 1"),
    false,
  );
  await accessible("flat rating inspection");
  await page.screenshot({
    path: "/tmp/mongodiff-rated-details.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Close modal", exact: true }).click();
  await openDetails("Run history");
  await page
    .getByRole("button", { name: "Model changes", exact: true })
    .click();
  await accessible("model changes");
  await page.getByRole("button", { name: "Close modal", exact: true }).click();
  for (const name of ["View validator", "Run history"]) {
    await openDetails(name);
    await accessible(name);
    await page.keyboard.press("Escape");
  }
  await page.getByLabel("Switch to dark theme").click();
  await page.screenshot({
    path: "/tmp/schema-guard-atlas-dark.png",
    fullPage: true,
  });
  await accessible("optional dark MongoDiff");
  await page.reload({ waitUntil: "networkidle" });
  assert.equal(await page.locator("html").getAttribute("data-theme"), "dark");
  await page.getByLabel("Switch to light theme").click();
  await checkScript();
  await page
    .getByRole("button", { name: "Apply Fix & Rescan", exact: true })
    .click();
  await accessible("fix confirmation");
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  assert.equal(
    await page.getByTestId("failure-count").textContent(),
    "7 of 12",
  );
  await page
    .getByRole("button", { name: "Apply Fix & Rescan", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Apply & Rescan", exact: true })
    .click();
  await page.getByText("7 → 0 failing documents", { exact: true }).waitFor();
  await accessible("fresh verification");
  assert.equal(
    await page.getByTestId("failure-count").textContent(),
    "0 of 12",
  );
  await page
    .getByRole("button", { name: "Apply Fix & Rescan", exact: true })
    .waitFor();
  assert.equal(
    await page
      .getByRole("button", { name: "Apply Fix & Rescan", exact: true })
      .isDisabled(),
    true,
  );
  await page.screenshot({
    path: "/tmp/schema-guard-repaired.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Reset demo data" }).click();
  await page
    .getByTestId("failure-count")
    .filter({ hasText: "7 of 12" })
    .waitFor();
  for (const width of [375, 768, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await accessible(`${width}px MongoDiff`);
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
      false,
      `${width}px overflow`,
    );
    for (const name of [
      "View validator",
      "Run history",
      "Details for runtime: Missing or empty value",
    ]) {
      await openDetails(name);
      await accessible(`${width}px ${name}`);
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth > innerWidth,
        ),
        false,
        `${width}px ${name} overflow`,
      );
      if (name.startsWith("Details")) {
        await page.getByText("Missing from document", { exact: true }).waitFor();
        assert.match(await page.getByRole("dialog").innerText(), /null/);
      }
      await page
        .getByRole("button", { name: "Close modal", exact: true })
        .click();
    }
    if (width === 375) {
      await page.screenshot({
        path: "/tmp/schema-guard-mobile.png",
        fullPage: true,
      });
      await page.getByLabel("Open collection explorer").click();
      assert.equal(
        await page.getByLabel("Open collection explorer").getAttribute("aria-expanded"),
        "true",
      );
      assert.equal(
        await page.getByRole("textbox", { name: "Filter collections", exact: true })
          .evaluate((element) => element === document.activeElement),
        true,
        "Opening the explorer moves focus to its filter",
      );
      await accessible("mobile collection explorer");
      await page.keyboard.press("Escape");
      assert.equal(
        await page.getByLabel("Open collection explorer").getAttribute("aria-expanded"),
        "false",
      );
      assert.equal(
        await page.getByLabel("Open collection explorer")
          .evaluate((element) => element === document.activeElement),
        true,
        "Closing the explorer restores focus to its trigger",
      );
      await page.getByLabel("Open collection explorer").click();
      await page.getByLabel("Close collection explorer").click();
    }
  }
  if (process.env.GUARD_SMOKE_AI === "1") {
    await page.setViewportSize({ width: 1440, height: 1000 });
    const [response] = await Promise.all([
      page.waitForResponse((response) => response.url().endsWith("/api/analyze") && response.request().postDataJSON()?.suggestions === true),
      page.getByRole("button", { name: "Voyage AI suggestions", exact: true }).click(),
    ]);
    const aiReport = await response.json();
    assert.equal(aiReport.failing, 7);
    assert.equal(aiReport.scan.suggestions.status, "ok", "Configured provider must succeed for the recording check");
    assert.equal(aiReport.scan.suggestions.provider, "voyage");
    await page.getByText(/Voyage AI suggestions/).waitFor();
    await openDetails("Details for rated: Missing or invalid value");
    await page.getByRole("button", { name: 'Use R for "NR"', exact: true }).waitFor();
    await accessible("Voyage suggestions modal");
    await page.screenshot({ path: "/tmp/mongodiff-ai-suggestions.png", fullPage: true });
    await page.setViewportSize({ width: 375, height: 900 });
    await accessible("375px AI suggestions modal");
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.setViewportSize({ width: 1440, height: 1000 });
    const [preview] = await Promise.all([
      page.waitForResponse((response) => response.url().endsWith("/plan") && response.request().postDataJSON()?.mappings?.rated?.NR === "R"),
      page.getByRole("button", { name: 'Use R for "NR"', exact: true }).click(),
    ]);
    const selectedPlan = await preview.json();
    assert.ok(selectedPlan.operations.some((operation) => operation.kind === "mapping" && operation.filter.$expr.$eq[1].$literal === "NR" && operation.update.$set.rated === "R"));
    assert.equal(await page.getByTestId("failure-count").textContent(), "7 of 12", "Selecting a suggestion only updates the preview");
    await page.getByRole("button", { name: "Apply Fix & Rescan", exact: true }).click();
    await page.getByRole("button", { name: "Apply & Rescan", exact: true }).click();
    await page.getByTestId("failure-count").filter({ hasText: "0 of 12" }).waitFor();
    await page.getByRole("button", { name: "Reset demo data" }).click();
    await page.getByTestId("failure-count").filter({ hasText: "7 of 12" }).waitFor();
    console.log("Passed: real Voyage suggestions, cached retakes, accessible mobile inspection, explicit mapping preview, and fixture repair 7→0.");
  }
  await page.getByRole("button", { name: "Data source", exact: true }).click();
  await page.getByRole("option", { name: /MongoDB Atlas/ }).click();
  await page
    .getByRole("button", { name: "Run analysis", exact: true })
    .first()
    .click();
  await page.getByRole("alert").waitFor();
  assert.match(
    await page.getByRole("alert").textContent(),
    /Atlas is not configured/,
  );
  await accessible("Atlas setup error");
  assert.deepEqual(errors, []);
  assert.deepEqual(consoleErrors, [], "No unexpected browser console errors");
  console.log(
    "Passed: simplified content, three accurate issue rows, no forms, displayed script matches API operations, reviewed fix 7→0, reset, inspection, supporting dialogs, themes, accessibility, and 375/768/1280px layouts.",
  );
} finally {
  await browser.close();
}
