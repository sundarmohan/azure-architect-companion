# Azure Architect Companion Frontend

React and TypeScript visual architecture designer for the backend canonical architecture model.

## Local setup

Requires Node.js 20 or newer.

```powershell
npm install
npm run dev
```

The Vite development server runs at `http://localhost:5173` and proxies `/api` requests to `http://localhost:8000`.

## Commands

```powershell
npm run build
npm run lint
npm test
```

Canvas coordinates are presentation metadata stored locally per architecture version. Canonical resources, hierarchy, relationships, dependencies, validation, compliance, and version comparison remain backend-owned.
