import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// Serious or critical WCAG 2.0/2.1 A/AA violations fail the build (light theme, signed
// out); minor ones don't.
async function expectAccessible(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(
    blocking.map((v) => `${v.id}: ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`),
  ).toEqual([]);
}

async function expectNoHorizontalScroll(page: Page) {
  const { sw, cw } = await page.evaluate(() => ({
    sw: document.documentElement.scrollWidth,
    cw: document.documentElement.clientWidth,
  }));
  expect(sw).toBeLessThanOrEqual(cw);
}

test("home: search and live numbers in the first view", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("searchbox", { name: "Search roles" })).toBeInViewport();
  await expect(page.getByText("Open roles", { exact: true })).toBeVisible();
  await expectNoHorizontalScroll(page);
  await expectAccessible(page);
});

test("feed: filters and role cards", async ({ page }) => {
  await page.goto("/jobs?level=intern");
  await expect(page.getByRole("heading", { name: "Open roles", level: 1 })).toBeVisible();
  await expect(page.getByRole("searchbox", { name: "Search roles" })).toBeVisible();
  await expect(page.locator('a[href^="/jobs/"]').first()).toBeVisible();
  await expectNoHorizontalScroll(page);
  await expectAccessible(page);
});

test("job detail: description, apply and metadata", async ({ page }) => {
  await page.goto("/jobs?level=intern");
  const href = await page.locator('article a[href^="/jobs/"]').first().getAttribute("href");
  expect(href).toMatch(/^\/jobs\/\d+$/);
  const response = await page.goto(href!);
  expect(response?.status()).toBe(200);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("link", { name: /Apply on .+ site/ }).first()).toBeAttached();
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", new RegExp(`${href}$`));
  await expectNoHorizontalScroll(page);
  await expectAccessible(page);
});

test("missing job is a real 404", async ({ page }) => {
  const response = await page.goto("/jobs/999999999");
  expect(response?.status()).toBe(404);
});

test("companies and a company page", async ({ page }) => {
  await page.goto("/companies");
  await expect(page.getByRole("heading", { name: "Companies", level: 1 })).toBeVisible();
  await expectAccessible(page);
  const first = page.locator('main ul a[href^="/companies/"]').first();
  const name = (await first.locator("h2").textContent())?.trim() ?? "";
  await first.click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(name);
  await expectNoHorizontalScroll(page);
  await expectAccessible(page);
});

test("mobile nav opens as a sheet", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "the menu button exists below lg only");
  await page.goto("/");
  await page.getByRole("button", { name: /menu/i }).click();
  const sheet = page.getByRole("dialog");
  await expect(sheet).toBeVisible();
  await expect(sheet.getByRole("link", { name: /companies/i }).first()).toBeVisible();
  await expectAccessible(page);
});

test("status page shows recent runs", async ({ page }) => {
  await page.goto("/status");
  await expect(page.getByRole("heading", { name: "Status", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recent runs" })).toBeVisible();
  await expect(page.locator("table tbody tr").first()).toBeVisible();
  await expectNoHorizontalScroll(page);
  await expectAccessible(page);
});
