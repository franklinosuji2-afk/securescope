import { defineConfig, devices } from "@playwright/test";

const python = process.env.E2E_PYTHON ?? "python";
const database =
  process.env.E2E_DATABASE_URL ?? "sqlite:////tmp/securescope-e2e.db";
const executablePath = process.env.PW_CHROMIUM_PATH || undefined;

/**
 * Real-browser tests against the real backend (no mocks). The backend runs with production safety
 * settings; nothing here can reach a private address or a third-party site except the DNS lookup
 * that the ownership check performs.
 */
export default defineConfig({
  testDir: "./e2e",
  testMatch: /.*\.e2e\.ts/,
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 30_000,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://localhost:4173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    // Animations are checked in their own test; everywhere else they would make contrast checks time-dependent.
    reducedMotion: "reduce",
    ...devices["Desktop Chrome"],
    launchOptions: executablePath ? { executablePath } : {},
  },
  webServer: [
    {
      command: `${python} -m app.database.migrate && ${python} -m uvicorn app.main:create_app --factory --port 8000`,
      cwd: "../backend",
      url: "http://localhost:8000/api/v1/health",
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        SECURESCOPE_DATABASE_URL: database,
        SECURESCOPE_COOKIE_SECURE: "false",
        // The default vulnerability source is "unavailable", so a scan here ends Failed and is not counted.
        SECURESCOPE_APP_SCANNING_ENABLED: "true",
        // The suite registers more accounts from one address than the production sign-up limit (10 per hour)
        // allows, and that in-memory limit lives as long as this server. Raised for this test server only.
        SECURESCOPE_REGISTRATIONS_PER_IP_PER_HOUR: "1000",
        SECURESCOPE_CORS_ORIGINS: '["http://localhost:4173"]',
      },
    },
    {
      command: "npm run build && npx vite preview --port 4173 --strictPort",
      url: "http://localhost:4173",
      reuseExistingServer: false,
      timeout: 120_000,
      env: { VITE_API_PROXY: "http://localhost:8000" },
    },
  ],
});
