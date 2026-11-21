$base = "http://127.0.0.1:8000"
$ErrorActionPreference = "Continue"

function Call-Api {
    param(
        [string]$Method,
        [string]$Path,
        $Body = $null
    )

    $url = "$base$Path"
    try {
        if ($null -ne $Body) {
            $json = $Body | ConvertTo-Json -Depth 15
            $resp = Invoke-RestMethod -Method $Method -Uri $url -ContentType "application/json" -Body $json
        }
        else {
            $resp = Invoke-RestMethod -Method $Method -Uri $url
        }

        $detail = "scalar"
        if ($resp -is [System.Collections.IEnumerable] -and -not ($resp -is [string])) {
            $arr = @($resp)
            $detail = "count=$($arr.Count)"
        }
        elseif ($null -ne $resp) {
            $props = @($resp.PSObject.Properties.Name)
            if ($props.Count -gt 0) {
                $detail = "keys=" + ($props -join ",")
            }
        }

        return [pscustomobject]@{
            method = $Method
            path = $Path
            ok = $true
            detail = $detail
        }
    }
    catch {
        return [pscustomobject]@{
            method = $Method
            path = $Path
            ok = $false
            detail = $_.Exception.Message
        }
    }
}

$results = @()
$archName = "v2202-audit-$(Get-Date -Format 'yyyyMMdd-HHmmss')"

try {
    $createResp = Invoke-RestMethod -Method POST -Uri "$base/api/architectures" -ContentType "application/json" -Body (@{
        name = $archName
        provider = "azure"
        environment = "draft"
        status = "draft"
        default_region = "eastus"
        graph_data = @{}
    } | ConvertTo-Json -Depth 10)
    $archId = [string]$createResp.id
    $results += [pscustomobject]@{ method = "POST"; path = "/api/architectures"; ok = $true; detail = "created:$archId" }
}
catch {
    $results += [pscustomobject]@{ method = "POST"; path = "/api/architectures"; ok = $false; detail = $_.Exception.Message }
    $results | ConvertTo-Json -Depth 8
    exit 1
}

$results += Call-Api -Method "GET" -Path "/api/architectures/$archId"
$results += Call-Api -Method "PUT" -Path "/api/architectures/$archId" -Body @{ description = "v2202 functional audit temporary architecture" }

$subResp = Invoke-RestMethod -Method POST -Uri "$base/api/architectures/$archId/subscriptions" -ContentType "application/json" -Body (@{
    name = "Audit Subscription"
    subscription_id = "audit-subscription"
    tenant_id = "audit-tenant"
    environment = "public"
    properties = @{ source = "audit" }
} | ConvertTo-Json)
$results += [pscustomobject]@{ method = "POST"; path = "/api/architectures/$archId/subscriptions"; ok = $true; detail = "created" }
$subId = $subResp.id

$rgResp = Invoke-RestMethod -Method POST -Uri "$base/api/architectures/$archId/resource-groups" -ContentType "application/json" -Body (@{
    name = "rg-audit"
    location = "eastus"
    subscription_id = $subId
    position_x = 120
    position_y = 80
    tags = @{ audit = "true" }
    properties = @{}
} | ConvertTo-Json)
$results += [pscustomobject]@{ method = "POST"; path = "/api/architectures/$archId/resource-groups"; ok = $true; detail = "created" }
$rgId = $rgResp.id

$r1 = Invoke-RestMethod -Method POST -Uri "$base/api/architectures/$archId/resources" -ContentType "application/json" -Body (@{
    resource_type = "vnet"
    azure_resource_type = "Microsoft.Network/virtualNetworks"
    name = "vnet-audit"
    location = "eastus"
    resource_group_id = $rgId
    position_x = 250
    position_y = 160
    properties = @{}
} | ConvertTo-Json)
$results += [pscustomobject]@{ method = "POST"; path = "/api/architectures/$archId/resources"; ok = $true; detail = "created vnet" }

$r2 = Invoke-RestMethod -Method POST -Uri "$base/api/architectures/$archId/resources" -ContentType "application/json" -Body (@{
    resource_type = "subnet"
    azure_resource_type = "Microsoft.Network/virtualNetworks/subnets"
    name = "subnet-audit"
    location = "eastus"
    resource_group_id = $rgId
    parent_resource_id = $r1.id
    position_x = 430
    position_y = 160
    properties = @{}
} | ConvertTo-Json)
$results += [pscustomobject]@{ method = "POST"; path = "/api/architectures/$archId/resources"; ok = $true; detail = "created subnet" }

$results += Call-Api -Method "POST" -Path "/api/architectures/$archId/validate-relationship" -Body @{
    source_resource_id = $r1.id
    target_resource_id = $r2.id
    relationship_type = "contains"
}
$results += Call-Api -Method "POST" -Path "/api/architectures/$archId/relationships" -Body @{
    source_resource_id = $r1.id
    target_resource_id = $r2.id
    relationship_type = "contains"
    properties = @{ audit = "true" }
}

$results += Call-Api -Method "GET" -Path "/api/architectures/$archId/subscriptions"
$results += Call-Api -Method "GET" -Path "/api/architectures/$archId/resource-groups"
$results += Call-Api -Method "GET" -Path "/api/architectures/$archId/resources"
$results += Call-Api -Method "GET" -Path "/api/architectures/$archId/relationships"
$results += Call-Api -Method "GET" -Path "/api/architectures/$archId/dependencies"

$results += Call-Api -Method "POST" -Path "/api/architectures/$archId/monitoring-summary" -Body @{}
$results += Call-Api -Method "POST" -Path "/api/architectures/$archId/alerts-summary" -Body @{}
$results += Call-Api -Method "POST" -Path "/api/architectures/$archId/incident-summary" -Body @{}
$results += Call-Api -Method "POST" -Path "/api/architectures/$archId/resources/$($r1.id)/monitoring" -Body @{}
$results += Call-Api -Method "POST" -Path "/api/architectures/$archId/cost-estimate" -Body @{}
$results += Call-Api -Method "POST" -Path "/api/architectures/$archId/actual-cost" -Body @{}
$results += Call-Api -Method "POST" -Path "/api/architectures/$archId/governance-summary" -Body @{}
$results += Call-Api -Method "POST" -Path "/api/architectures/$archId/security-summary" -Body @{}
$results += Call-Api -Method "POST" -Path "/api/architectures/$archId/intelligence-analysis" -Body @{ provider = "deterministic_fallback" }
$results += Call-Api -Method "POST" -Path "/api/reports/architectures/$archId/executive-summary" -Body @{ provider = "deterministic_fallback"; include_actual_cost = $false }

$results += Call-Api -Method "GET" -Path "/api/azure/resource-catalog"
$results += Call-Api -Method "GET" -Path "/api/settings"
$results += Call-Api -Method "GET" -Path "/api/settings/azure/status"
$results += Call-Api -Method "POST" -Path "/api/settings/azure/test"
$results += Call-Api -Method "POST" -Path "/api/settings/providers/openai/test"
$results += Call-Api -Method "POST" -Path "/api/settings/providers/gemini/test"

$existingArch = "c7cfcc32-ff34-4d6b-ab20-fbed5e78cd9b"
$incidentList = @(Invoke-RestMethod -Method GET -Uri "$base/api/architectures/$existingArch/incidents")
if ($incidentList.Count -gt 0) {
    $incidentId = [string]($incidentList | Select-Object -ExpandProperty incident_id -First 1)
    $incidentStatus = [string]($incidentList | Select-Object -ExpandProperty status -First 1)
    $results += Call-Api -Method "GET" -Path "/api/architectures/$existingArch/incidents/$incidentId"
    $results += Call-Api -Method "PUT" -Path "/api/architectures/$existingArch/incidents/$incidentId/status" -Body @{ status = $incidentStatus; comment = "v2202 audit no-op"; actor = "audit-bot" }
}

$results += Call-Api -Method "DELETE" -Path "/api/architectures/$archId"

$results | ConvertTo-Json -Depth 8
