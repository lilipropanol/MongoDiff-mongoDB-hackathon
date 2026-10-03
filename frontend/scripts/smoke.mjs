import { chromium } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import assert from 'node:assert/strict';

const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome' });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
async function settle() {
  await page.evaluate(() => Promise.all(Array.from(document.querySelectorAll('.view-enter')).flatMap(el => el.getAnimations().map(animation => animation.finished))));
}
try {
  await page.goto(process.argv[2] || process.env.GUARD_UI_URL || 'http://127.0.0.1:8000', { waitUntil: 'networkidle' });
  await page.getByText('Schema change needs attention').waitFor();
  await settle();
  assert.equal(await page.locator('.summary-number strong').textContent(), '7');
  await page.screenshot({ path: '/tmp/schema-guard-desktop.png', fullPage: true });
  for (const name of ['Impact report', 'Model changes', 'Fix preview', 'Validator', 'Run history']) {
    await page.getByRole('tab', { name }).click();
    await settle();
    const accessibility = await new AxeBuilder({ page }).analyze();
    assert.deepEqual(accessibility.violations.map(v => ({ id: v.id, nodes: v.nodes.map(n => ({ html: n.html, summary: n.failureSummary })) })), [], `${name} accessibility`);
  }
  await page.getByRole('tab', { name: 'Fix preview' }).click();
  await page.getByRole('button', { name: 'Use demo decisions' }).click();
  await page.getByRole('button', { name: 'Preview fix plan' }).click();
  await page.getByRole('button', { name: 'Apply to demo data' }).click();
  await page.getByRole('dialog').waitFor();
  await settle();
  assert.deepEqual((await new AxeBuilder({ page }).analyze()).violations.map(v => v.id), [], 'confirmation accessibility');
  await page.getByRole('button', { name: 'Apply demo plan', exact: true }).click();
  await page.getByText('The collection matches the proposed schema').waitFor();
  await settle();
  assert.equal(await page.locator('.summary-number strong').textContent(), '0');
  await page.screenshot({ path: '/tmp/schema-guard-repaired.png', fullPage: true });
  await page.getByRole('button', { name: 'Reset demo data' }).click();
  await page.getByText('Schema change needs attention').waitFor();
  assert.equal(await page.locator('.summary-number strong').textContent(), '7');
  for (const width of [375, 768, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    for (const name of ['Impact report', 'Model changes', 'Fix preview', 'Validator', 'Run history']) {
      await page.getByRole('tab', { name }).click();
      await settle();
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `${name}: ${width}px overflow`);
    }
    assert.deepEqual((await new AxeBuilder({ page }).analyze()).violations.map(v => ({ id: v.id, nodes: v.nodes.length })), [], `${width}px accessibility`);
    if (width === 375) {
      await page.getByRole('tab', { name: 'Impact report' }).click();
      await page.screenshot({ path: '/tmp/schema-guard-mobile.png', fullPage: true });
    }
  }
  await page.getByLabel('Data source').selectOption('atlas');
  await page.getByRole('button', { name: 'Run analysis', exact: true }).first().click();
  await page.getByRole('alert').waitFor();
  assert.match(await page.getByRole('alert').textContent(), /Atlas is not configured/);
  assert.deepEqual(errors, []);
  console.log('Passed: demo 7→0, reset, five tabs, confirmation, Atlas setup error, accessibility, and 375/768/1280px layouts.');
} finally {
  await browser.close();
}
