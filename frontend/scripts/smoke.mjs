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
const page = await context.newPage();
const errors = [],
  plans = [];
page.on("pageerror", (error) => errors.push(error.message));
page.on("response", async (response) => {
  if (response.url().endsWith("/plan") && response.ok())
    plans.push(await response.json());
});
async function settle() {
  await page.evaluate(() =>
    Promise.all(
      Array.from(document.querySelectorAll(".view-enter")).flatMap((el) =>
        el.getAnimations().map((animation) => animation.finished),
      ),
    ),
  );
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
        name: "Download schema_guard_fix.js",
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
  await settle();
  assert.equal(
    await page.getByTestId("failure-count").textContent(),
    "7 of 12",
  );
  assert.equal(
    await page
      .getByRole("tab", { name: /Schema Guard/ })
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
  await page.getByText("MongoDB Atlas Schema Guard · v1.0.0").waitFor();
  await checkScript();
  await page.screenshot({
    path: "/tmp/schema-guard-atlas-dark.png",
    fullPage: true,
  });
  await accessible("simplified dark Schema Guard");
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
  await accessible("grouped rating inspection");
  await page.getByLabel("Close detail panel").click();
  await openDetails("Run history");
  await page
    .getByRole("button", { name: "Model changes", exact: true })
    .click();
  await accessible("model changes");
  await page.getByLabel("Close detail panel").click();
  for (const name of ["View validator", "Run history"]) {
    await openDetails(name);
    await accessible(name);
    await page.keyboard.press("Escape");
  }
  await page.getByLabel("Switch to light theme").click();
  await page.screenshot({
    path: "/tmp/schema-guard-atlas-light.png",
    fullPage: true,
  });
  await accessible("simplified light Schema Guard");
  await page.reload({ waitUntil: "networkidle" });
  assert.equal(await page.locator("html").getAttribute("data-theme"), "light");
  await page.getByLabel("Switch to dark theme").click();
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
    await accessible(`${width}px Schema Guard`);
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
      false,
      `${width}px overflow`,
    );
    for (const name of ["View validator", "Run history"]) {
      await openDetails(name);
      await accessible(`${width}px ${name}`);
      await page.getByLabel("Close detail panel").click();
    }
    if (width === 375) {
      await page.screenshot({
        path: "/tmp/schema-guard-mobile.png",
        fullPage: true,
      });
      await page.getByLabel("Open collection explorer").click();
      await page.getByLabel("Close collection explorer").click();
    }
  }
  await page.getByLabel("Data source").selectOption("atlas");
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
  console.log(
    "Passed: simplified content, three accurate issue rows, no forms, displayed script matches API operations, reviewed fix 7→0, reset, inspection, supporting dialogs, themes, accessibility, and 375/768/1280px layouts.",
  );
} finally {
  await browser.close();
}
