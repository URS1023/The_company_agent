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
  await expect(page.getByText("e2e.txt")).toBeVisible();

  await page.goto("/knowledge");
  await page.getByLabel("知识库名称").fill("E2E 知识库");
  await page.getByRole("button", { name: "创建知识库" }).click();
  await expect(page.getByText("E2E 知识库")).toBeVisible();
});
