import { expect, test } from "@playwright/test";

test.describe("public and navigation surfaces", () => {
  test("landing page presents the product thesis and entry points", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle("企业 AI 工作台");
    await expect(page.getByRole("heading", { name: "把一项工作，变成一条可复用的路径。" })).toBeVisible();
    await expect(page.getByRole("link", { name: "进入工作台" })).toBeVisible();
    await expect(page.getByRole("link", { name: "管理员登录" })).toBeVisible();
  });

  test("login and first-login password pages expose accessible forms", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "登录工作区" })).toBeVisible();
    await expect(page.getByLabel("登录名")).toBeVisible();
    await expect(page.getByLabel("密码")).toBeVisible();
    await page.goto("/first-login/password");
    await expect(page.getByRole("heading", { name: "设置你的工作区密码" })).toBeVisible();
    await expect(page.getByLabel("当前密码")).toBeVisible();
    await expect(page.getByLabel(/新密码/)).toBeVisible();
  });

  test("chat shell exposes business navigation and composer", async ({ page }, testInfo) => {
    await page.goto("/chat");
    await expect(page.getByRole("heading", { name: "今天要完成什么工作？" })).toBeVisible();
    await expect(page.getByRole("textbox", { name: "消息输入" })).toBeVisible();
    if (testInfo.project.name === "mobile-chromium") {
      await page.getByRole("button", { name: "打开导航" }).click();
    }
    await expect(page.getByRole("link", { name: "知识库" })).toHaveAttribute("href", "/knowledge");
    await expect(page.getByRole("link", { name: "插件" })).toHaveAttribute("href", "/plugins");
    if (testInfo.project.name === "chromium") {
      await expect(page.getByText("证据轨道")).toBeVisible();
    }
  });

  test("management pages render empty/error states without crashing", async ({ page }) => {
    for (const [path, heading] of [
      ["/admin/members", "成员与权限"],
      ["/knowledge", "知识库"],
      ["/plugins", "插件"],
      ["/files", "文件"],
      ["/data-sources", "数据源"]
    ] as const) {
      await page.goto(path);
      await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    }
  });

  test("mobile chat keeps the composer within the viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/chat");
    await expect(page.getByRole("textbox", { name: "消息输入" })).toBeVisible();
    const bodyWidth = await page.locator("body").evaluate((node) => node.scrollWidth);
    const viewportWidth = await page.evaluate(() => window.innerWidth);
    expect(bodyWidth).toBeLessThanOrEqual(viewportWidth + 1);
  });
});
