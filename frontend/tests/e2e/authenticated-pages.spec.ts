import { expect, test } from "@playwright/test";

test("admin can create a member, upload a file, and create a knowledge base", async ({ page }, testInfo) => {
  await page.goto("/login");
  await page.getByLabel("登录名").fill("workspace-admin");
  await page.getByLabel("密码").fill("e2e-admin-password-123");
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page).toHaveURL(/\/chat$/);

  await page.goto("/admin/members");
  await expect(page.getByRole("heading", { name: "成员与权限" })).toBeVisible();
  await page.getByLabel("登录名").fill(`e2e-member-${testInfo.project.name}`);
  await page.getByLabel("显示名称").fill("E2E 成员");
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(page.getByText(/临时密码/)).toBeVisible();

  await page.goto("/files");
  await page.locator('input[type="file"]').setInputFiles({
    name: "e2e.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("E2E knowledge source")
  });
  await expect(page.getByRole("heading", { name: "e2e.txt" }).first()).toBeVisible();

  await page.goto("/knowledge");
  await page.getByLabel("知识库名称").fill("E2E 知识库");
  await page.getByRole("button", { name: "创建知识库" }).click();
  await expect(page.getByRole("heading", { name: "E2E 知识库" }).first()).toBeVisible();

  await page.goto("/plugins");
  await page.getByLabel("插件名称").fill(`E2E 插件 ${testInfo.project.name}`);
  await page.getByRole("button", { name: "创建并发布" }).click();
  await expect(page.getByRole("heading", { name: `E2E 插件 ${testInfo.project.name}` }).first()).toBeVisible();

  await page.getByRole("button", { name: "复制" }).first().click();
  await expect(page.getByText(/副本/).first()).toBeVisible();
  await page.getByRole("button", { name: /分享给 Workspace/ }).first().click();

  await page.goto("/admin/models");
  await expect(page.getByRole("heading", { name: "模型配置" })).toBeVisible();
  await page.goto("/admin/audit");
  await expect(page.getByRole("heading", { name: "审计日志" })).toBeVisible();
  await page.goto("/admin/secrets");
  await expect(page.getByRole("heading", { name: "Secret", exact: true })).toBeVisible();

  await page.goto("/chat");
  await page.getByLabel("消息输入").fill("检查当前运行轨迹");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("link", { name: "执行详情" })).toBeVisible({ timeout: 10000 });
  await page.getByRole("link", { name: "执行详情" }).click();
  await expect(page.getByRole("heading", { name: "执行详情" })).toBeVisible();

  await page.goto("/demos");
  await page.getByRole("button", { name: "运行招投标分析" }).click();
  await expect(page.getByRole("heading", { name: "结构化结果" })).toBeVisible();
  await page.getByRole("button", { name: "运行财务分析" }).click();
  await expect(page.getByRole("heading", { name: "结构化结果" })).toBeVisible();
});
