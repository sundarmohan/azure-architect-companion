const { readFileSync } = require("node:fs");
const { chromium } = require("playwright-core");

let stage = "read bootstrap settings";

async function verify() {
  const settings = Object.fromEntries(readFileSync("bootstrap", "utf8").trim()
    .split("\n").map((line) => line.split(/=(.*)/s, 2)));
  const browser = await chromium.launch({ channel: "chrome" });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on("pageerror", () => errors.push("Uncaught browser exception"));
    page.on("response", (response) => {
      if (response.status() >= 500) errors.push("HTTP server error in browser");
    });
    await page.goto("http://localhost:8003/");
    await page.getByRole("heading", { name: "Sign in to MonitorAI" }).waitFor();
    await page.getByLabel("Username").fill(settings.MONITORAI_BOOTSTRAP_USERNAME);
    await page.getByLabel("Password", { exact: true }).fill(settings.MONITORAI_BOOTSTRAP_PASSWORD);
    const login = page.waitForResponse((response) => response.url().endsWith("/api/auth/login"));
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    if (!(await login).ok()) throw new Error("Browser sign-in failed");

    const navigation = page.getByRole("navigation", { name: "Workspace navigation" });
    await navigation.getByRole("button", { name: "Account", exact: true }).waitFor();
    const architecture = navigation.getByRole("button", { name: "Architecture Studio" });
    if (!(await architecture.isVisible())) {
      await page.getByRole("heading", { name: "Account", exact: true }).waitFor();
      const createClient = page.locator("form").filter({ has: page.getByRole("heading", { name: "Create client" }) });
      await createClient.getByLabel("Client name").fill("Review workspace");
      await createClient.getByRole("button", { name: "Create client" }).click();
    }
    await architecture.waitFor();
    const response = await page.request.get("http://localhost:8003/api/auth/me");
    // The API request context shares the browser's authenticated cookies.
    if (!response.ok() || !(await response.json()).is_platform_admin) throw new Error("Administrator API session failed");

    for (const label of ["Architecture Studio", "Azure Inventory", "Monitoring", "Network", "Security", "Assessments", "Azure Connection", "Account"]) {
      const button = navigation.getByRole("button", { name: label, exact: true });
      await button.click();
      await navigation.locator(".active").filter({ hasText: label }).waitFor();
      await page.getByRole("main").getByRole("heading", { level: 1 }).waitFor();
      console.log(`Workspace rendered: ${label}`);
    }
    await page.getByRole("button", { name: "Sign out" }).click();
    await page.getByRole("heading", { name: "Sign in to MonitorAI" }).waitFor();
    if (errors.length) throw new Error(errors.join(", "));
    console.log("Browser sign-in, authenticated API, navigation and sign-out passed");
  } finally {
    await browser.close();
  }
}

verify().catch((error) => {
  // Keep Playwright call logs out of CI because they may include filled inputs.
  console.error(`Browser check failed during ${stage} (${error.name})`);
  process.exitCode = 1;
});
