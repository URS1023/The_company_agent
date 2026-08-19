import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  timeout: 30_000,
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure"
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-chromium", use: { ...devices["Pixel 5"] } }
  ],
  webServer: [
    {
      command: "powershell -NoProfile -ExecutionPolicy Bypass -File ../scripts/run-e2e-api.ps1",
      url: "http://127.0.0.1:8000/api/v1/health/live",
      reuseExistingServer: false,
      timeout: 120_000,
      cwd: "."
    },
    {
      command: "E:/Environment_f/nvm_f/v22.13.0/npm.cmd run dev",
      url: "http://127.0.0.1:3000",
      reuseExistingServer: true,
      timeout: 120_000,
      cwd: "."
    }
  ]
});
