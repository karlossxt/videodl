const fs = require("node:fs");
const path = require("node:path");
const { defineConfig, devices } = require("@playwright/test");

const venvPython =
  process.platform === "win32"
    ? path.join(".venv", "Scripts", "python.exe")
    : path.join(".venv", "bin", "python");
const python = process.env.PYTHON || (fs.existsSync(venvPython) ? venvPython : "python");

const PORT = Number(process.env.E2E_PORT || 8010);
const baseURL = `http://127.0.0.1:${PORT}`;

module.exports = defineConfig({
  testDir: "./tests/e2e",
  timeout: 90_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: `"${python}" -m uvicorn videodl.app:app --host 127.0.0.1 --port ${PORT}`,
    url: `${baseURL}/api/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: "pipe",
    stderr: "pipe",
  },
});
