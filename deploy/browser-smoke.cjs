const { chromium } = require("playwright-core");

async function verify() {
  const origin = new URL(process.env.MONITORAI_PUBLIC_URL);
  if (origin.protocol !== "https:" || origin.username || origin.password ||
      origin.pathname !== "/" || origin.search || origin.hash) {
    throw new Error("MONITORAI_PUBLIC_URL must be a public HTTPS origin");
  }

  const browser = await chromium.launch({ channel: "chrome" });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on("pageerror", () => errors.push("Uncaught browser exception"));
    page.on("response", (response) => {
      if (response.status() >= 500) errors.push("Server error during page load");
    });
    const [root, session] = await Promise.all([
      page.goto(origin.href, { timeout: 30000 }),
      page.waitForResponse((response) => response.url() === new URL("/api/auth/me", origin).href),
    ]);
    if (!root?.ok() || new URL(page.url()).origin !== origin.origin) {
      throw new Error("Public UI returned an unexpected HTTP status or origin");
    }
    await page.getByRole("heading", { name: "Sign in to MonitorAI" }).waitFor();
    await page.getByLabel("Username").waitFor();
    await page.getByLabel("Password", { exact: true }).waitFor();
    if (session.status() !== 401) throw new Error("Protected API did not return 401");
    const health = await page.request.get(new URL("/health", origin).href);
    if (!health.ok() || (await health.json()).status !== "ok") {
      throw new Error("Public health check failed");
    }
    if (errors.length) throw new Error(errors.join(", "));
    console.log("Public Chromium verified trusted TLS, the rendered sign-in form, same-origin API, and health.");
  } finally {
    await browser.close();
  }
}

verify().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
