import { useMemo, useState } from "react";
import PlatformDashboard from "./workspaces/PlatformDashboard";
import ArchitectureWorkspace from "./workspaces/ArchitectureWorkspace";
import MonitoringWorkspace from "./workspaces/MonitoringWorkspace";
import CostWorkspace from "./workspaces/CostWorkspace";
import GovernanceWorkspace from "./workspaces/GovernanceWorkspace";
import IntelligenceWorkspace from "./workspaces/IntelligenceWorkspace";
import ReportsWorkspace from "./workspaces/ReportsWorkspace";
import SettingsWorkspace from "./workspaces/SettingsWorkspace";
import "./styles/app.css";
import "./styles/platform.css";

const NAV = [
  { id: "dashboard", label: "Dashboard" },
  { id: "architecture", label: "Architecture Studio" },
  { id: "monitoring", label: "Monitoring" },
  { id: "cost", label: "Cost / FinOps" },
  { id: "governance", label: "Governance / Security / Compliance" },
  { id: "intelligence", label: "Intelligence / AI" },
  { id: "reports", label: "Reports" },
  { id: "settings", label: "Settings" },
];

export default function App() {
  const [workspace, setWorkspace] = useState("dashboard");

  const content = useMemo(() => {
    if (workspace === "dashboard") {
      return (
        <PlatformDashboard
          onOpenArchitectureStudio={() => setWorkspace("architecture")}
          onOpenSettings={() => setWorkspace("settings")}
        />
      );
    }
    if (workspace === "architecture") {
      return <ArchitectureWorkspace />;
    }
    if (workspace === "monitoring") {
      return <MonitoringWorkspace />;
    }
    if (workspace === "cost") {
      return <CostWorkspace />;
    }
    if (workspace === "governance") {
      return <GovernanceWorkspace />;
    }
    if (workspace === "intelligence") {
      return <IntelligenceWorkspace />;
    }
    if (workspace === "settings") {
      return <SettingsWorkspace />;
    }
    return <ReportsWorkspace />;
  }, [workspace]);

  return (
    <div className="app-shell">
      <aside className="app-nav">
        <div className="brand">MONITORAI PLATFORM</div>
        <nav className="nav-list" aria-label="Workspace navigation">
          {NAV.map((item) => (
            <button
              key={item.id}
              className={`nav-item ${workspace === item.id ? "active" : ""}`}
              onClick={() => setWorkspace(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </aside>

      <main className="app-main">{content}</main>
    </div>
  );
}
