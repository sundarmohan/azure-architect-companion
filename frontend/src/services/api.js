const API=import.meta.env.VITE_API_URL||"http://127.0.0.1:8000/api";
const GET_CACHE_TTL_MS=30_000;
const getCache=new Map();
const getInFlight=new Map();
let cacheGeneration=0;
let clientId="";
let sessionGeneration=0;
let unauthorizedHandler;

export function setApiSession(nextClientId=""){
 clientId=nextClientId;
 sessionGeneration+=1;
 clearApiGetCache();
}

export function onUnauthorized(handler){
 unauthorizedHandler=handler;
 return ()=>{ if(unauthorizedHandler===handler) unauthorizedHandler=undefined; };
}

function cacheKey(path){return `${sessionGeneration}:${API}${path}`;}

async function fetchRequest(path,options={}){
 const generation=sessionGeneration;
 const authRoute=path.startsWith("/auth/");
 const {responseType,...fetchOptions}=options;
 const method=(options.method||"GET").toUpperCase();
 const headers=new Headers(options.headers);
 if(options.body) headers.set("Content-Type","application/json");
 if(method!=="GET") headers.set("X-MonitorAI-Request","1");
 if(clientId&&!authRoute) headers.set("X-Client-ID",clientId);
 const r=await fetch(`${API}${path}`,{...fetchOptions,headers,credentials:"include",cache:"no-store"});
 const verifySession=()=>{
  if(!authRoute&&generation!==sessionGeneration){
   throw new DOMException("The active client changed.","AbortError");
  }
 };
 verifySession();
 if(!r.ok){
  let message=`HTTP ${r.status}`;
  try{
   const raw=await r.text();
   const payload=raw?JSON.parse(raw):null;
   if(typeof payload?.detail==="string")message=payload.detail;
   else if(typeof payload?.detail?.message==="string")message=payload.detail.message;
  }catch{ /* A proxy may return a non-JSON error. */ }
  verifySession();
  if(r.status===401&&generation===sessionGeneration&&!["/auth/login","/auth/me"].includes(path)){
   unauthorizedHandler?.();
  }
  const error=new Error(message);
  error.status=r.status;
  throw error;
 }
 const data=r.status===204?null:responseType==="blob"?await r.blob():await r.json();
 verifySession();
 return data;
}

function refreshGet(path,options){
 const key=cacheKey(path);
 if(getInFlight.has(key)) return getInFlight.get(key);
 const generation=cacheGeneration;
 const requestPromise=fetchRequest(path,options).then((data)=>{
  if(generation===cacheGeneration) getCache.set(key,{data,storedAt:Date.now()});
  return data;
 }).finally(()=>{
  if(getInFlight.get(key)===requestPromise) getInFlight.delete(key);
 });
 getInFlight.set(key,requestPromise);
 return requestPromise;
}

async function request(path,options={}){
 const method=(options.method||"GET").toUpperCase();
 if(method!=="GET") return fetchRequest(path,options).then((data)=>{
  clearApiGetCache();
  return data;
 });

 const key=cacheKey(path);
 const cached=getCache.get(key);
 if(cached && Date.now()-cached.storedAt<GET_CACHE_TTL_MS){
  // Return the last good response immediately while refreshing it once in the background.
  void refreshGet(path,options).catch(()=>{});
  return cached.data;
 }
 return refreshGet(path,options);
}

export function clearApiGetCache(){
 cacheGeneration+=1;
 getCache.clear();
 getInFlight.clear();
}

const authWrite=(path,data)=>fetchRequest(`/auth/${path}`,{
 method:"POST",
 ...(data===undefined?{}:{body:JSON.stringify(data)}),
});
export const login=(username,password)=>authWrite("login",{username,password});
export const logout=()=>authWrite("logout");
export const getCurrentUser=()=>fetchRequest("/auth/me");
export const getClientAudit=signal=>fetchRequest("/audit",{signal});
export const getPlatformAudit=signal=>fetchRequest("/auth/audit",{signal});
export const changePassword=data=>authWrite("password",data);
export const createUser=data=>authWrite("users",data);
export const resetUserPassword=(username,data)=>authWrite(`users/${encodeURIComponent(username)}/password`,data);
export const createClient=data=>authWrite("clients",data);
export const setClientMember=(id,data)=>authWrite(`clients/${encodeURIComponent(id)}/members`,data);
export const listArchitectures=()=>request("/architectures");
export const createArchitecture=data=>request("/architectures",{method:"POST",body:JSON.stringify(data)});
export const updateArchitecture=(id,data)=>request(`/architectures/${id}`,{method:"PUT",body:JSON.stringify(data)});
export const deleteArchitecture=id=>request(`/architectures/${id}`,{method:"DELETE"});
export const duplicateArchitecture=(id,data)=>request(`/architectures/${id}/duplicate`,{method:"POST",body:JSON.stringify(data)});
export const transitionArchitecture=(id,data)=>request(`/architectures/${id}/status`,{method:"POST",body:JSON.stringify(data)});
export const listDesignHistory=id=>request(`/architectures/${id}/history`);
export const listDesignRevisions=id=>request(`/architectures/${id}/revisions`);
export const saveDesignRevision=(id,data)=>request(`/architectures/${id}/revisions`,{method:"POST",body:JSON.stringify(data)});
export const getDesignRevision=(id,revision)=>request(`/architectures/${id}/revisions/${revision}`);
export const compareDesignRevisions=(id,from,to)=>request(`/architectures/${id}/revisions/${from}/compare?to=${encodeURIComponent(to)}`);
export const restoreDesignRevision=(id,revision,data)=>request(`/architectures/${id}/revisions/${revision}/restore`,{method:"POST",body:JSON.stringify(data)});
export const getDesignValidation=id=>request(`/architectures/${id}/validation`);
export const getDesignExport=(id,format)=>fetchRequest(`/architectures/${id}/exports/${format}`,{responseType:"blob"});
export const getAnsibleExport=(id,data)=>fetchRequest(`/architectures/${id}/exports/ansible`,{
 method:"POST",body:JSON.stringify(data),responseType:"blob",
});
export const listResources=id=>request(`/architectures/${id}/resources`);
export const createResource=(id,data)=>request(`/architectures/${id}/resources`,{method:"POST",body:JSON.stringify(data)});
export const updateResource=(aid,rid,data)=>request(`/architectures/${aid}/resources/${rid}`,{method:"PUT",body:JSON.stringify(data)});
export const deleteResource=(aid,rid)=>request(`/architectures/${aid}/resources/${rid}`,{method:"DELETE"});
export const listRelationships=id=>request(`/architectures/${id}/relationships`);
export const createRelationship=(id,data)=>request(`/architectures/${id}/relationships`,{method:"POST",body:JSON.stringify(data)});
export const deleteRelationship=(aid,rid)=>request(`/architectures/${aid}/relationships/${rid}`,{method:"DELETE"});
export const validateRelationship=(id,data)=>request(`/architectures/${id}/validate-relationship`,{method:"POST",body:JSON.stringify(data)});

export const listSubscriptions=id=>request(`/architectures/${id}/subscriptions`);
export const createSubscription=(id,data)=>request(`/architectures/${id}/subscriptions`,{method:"POST",body:JSON.stringify(data)});
export const listResourceGroups=id=>request(`/architectures/${id}/resource-groups`);
export const createResourceGroup=(id,data)=>request(`/architectures/${id}/resource-groups`,{method:"POST",body:JSON.stringify(data)});
export const updateResourceGroup=(aid,rgid,data)=>request(`/architectures/${aid}/resource-groups/${rgid}`,{method:"PUT",body:JSON.stringify(data)});
export const deleteResourceGroup=(aid,rgid)=>request(`/architectures/${aid}/resource-groups/${rgid}`,{method:"DELETE"});
export const listDependencies=id=>request(`/architectures/${id}/dependencies`);
export const listAzureResourceCatalog=()=>request("/azure/resource-catalog");
export const listAzureResourceCapabilities=()=>request("/azure/resource-capabilities");
export const listAzureArchitecturePatterns=()=>request("/azure/architecture-patterns");
export const listAzureResourceConfigurations=()=>request("/azure/resource-configurations");
const subscriptionQuery=id=>id?`?subscription_id=${encodeURIComponent(id)}`:"";
export const getAzureActualCost=(id,start,end)=>fetchRequest(`/azure/cost/actual?${new URLSearchParams({subscription_id:id,start_date:start,end_date:end})}`);
export const getAzureCostBudget=id=>fetchRequest(`/azure/cost/budget${subscriptionQuery(id)}`);
export const saveAzureCostBudget=(id,data)=>request(`/azure/cost/budget${subscriptionQuery(id)}`,{method:"PUT",body:JSON.stringify(data)});
export const getAzureRecoveryObjectives=id=>fetchRequest(`/azure/backup/objectives${subscriptionQuery(id)}`);
export const saveAzureRecoveryObjectives=(id,data)=>request(`/azure/backup/objectives${subscriptionQuery(id)}`,{method:"PUT",body:JSON.stringify(data)});
export const getAzureBackupEvidence=id=>fetchRequest(`/azure/backup/evidence${subscriptionQuery(id)}`);
export const getComplianceReviews=id=>fetchRequest(`/compliance/reviews${subscriptionQuery(id)}`);
export const saveComplianceReview=(id,topic,data)=>request(`/compliance/reviews/${encodeURIComponent(topic)}${subscriptionQuery(id)}`,{method:"PUT",body:JSON.stringify(data)});
export const getDevSecOpsFindings=page=>fetchRequest(`/devsecops/findings?${new URLSearchParams({page})}`);
export const importDevSecOpsFindings=data=>request("/devsecops/findings/import",{method:"POST",body:JSON.stringify(data)});
export const getGitHubConnection=()=>fetchRequest("/devsecops/github/connection");
export const getGitHubDependencyAlerts=()=>fetchRequest("/devsecops/github/dependencies");
export const saveGitHubConnection=data=>request("/devsecops/github/connection",{method:"PUT",body:JSON.stringify(data)});
export const clearGitHubConnection=()=>request("/devsecops/github/connection",{method:"DELETE"});
export const getAzureCostRecommendations=id=>fetchRequest(`/azure/cost/recommendations${subscriptionQuery(id)}`);
export const getComplianceReviewHistory=(subscription,topic,page)=>fetchRequest(`/compliance/reviews/${encodeURIComponent(topic)}/history?${new URLSearchParams({subscription_id:subscription,page})}`);
export const getComplianceCatalog=()=>fetchRequest("/compliance/catalog");
export const getGitHubPipeline=(owner,repository)=>fetchRequest(`/devsecops/github/runs?${new URLSearchParams({owner,repository})}`);
export const getAzureInventory=id=>fetchRequest(`/azure/inventory${subscriptionQuery(id)}`);
export const refreshAzureInventory=id=>request(`/azure/inventory/refresh${subscriptionQuery(id)}`,{method:"POST"});
export const getAzureMonitoring=id=>fetchRequest(`/azure/monitoring${subscriptionQuery(id)}`);
export const refreshAzureMonitoring=id=>request(`/azure/monitoring/refresh${subscriptionQuery(id)}`,{method:"POST"});
export const getAzureMetricThreshold=id=>fetchRequest(`/azure/monitoring/thresholds${subscriptionQuery(id)}`);
export const saveAzureMetricThreshold=(id,data)=>request(`/azure/monitoring/thresholds${subscriptionQuery(id)}`,{
 method:"PUT",body:JSON.stringify(data),
});
export const queryAzureDiagnostics=(id,data)=>fetchRequest(`/azure/diagnostics/query${subscriptionQuery(id)}`,{
 method:"POST",body:JSON.stringify(data),
});
export const acknowledgeAzureHealthAlert=(subscription,evidenceId)=>request(
 `/azure/monitoring/health-alerts/${encodeURIComponent(evidenceId)}/acknowledgement${subscriptionQuery(subscription)}`,
 {method:"PUT"},
);
export const getAzureHealthIncidents=(subscription,page)=>fetchRequest(
 `/azure/monitoring/health-incidents?subscription_id=${encodeURIComponent(subscription)}&page=${page}`,
);
export const getAzureIncidentAttention=subscription=>fetchRequest(
 `/azure/monitoring/health-incidents/attention${subscriptionQuery(subscription)}`,
);
export const createAzureHealthIncident=(subscription,evidenceId)=>request(
 `/azure/monitoring/health-alerts/${encodeURIComponent(evidenceId)}/incident${subscriptionQuery(subscription)}`,
 {method:"PUT"},
);
export const updateAzureHealthIncident=(subscription,id,data)=>request(
 `/azure/monitoring/health-incidents/${encodeURIComponent(id)}${subscriptionQuery(subscription)}`,
 {method:"PUT",body:JSON.stringify(data)},
);
export const getAzureHealthIncidentActions=(subscription,id)=>fetchRequest(
 `/azure/monitoring/health-incidents/${encodeURIComponent(id)}/actions${subscriptionQuery(subscription)}`,
);
export const saveAzureHealthIncidentAction=(subscription,incidentId,actionId,data)=>request(
 `/azure/monitoring/health-incidents/${encodeURIComponent(incidentId)}/actions/${encodeURIComponent(actionId)}${subscriptionQuery(subscription)}`,
 {method:"PUT",body:JSON.stringify(data)},
);
export const getAzureIncidentSecurityEvidence=(subscription,incidentId)=>fetchRequest(
 `/azure/monitoring/health-incidents/${encodeURIComponent(incidentId)}/security-evidence${subscriptionQuery(subscription)}`,
);
export const linkAzureIncidentSecurityEvidence=(subscription,incidentId,findingId,collectedAt)=>request(
 `/azure/monitoring/health-incidents/${encodeURIComponent(incidentId)}/security-evidence/${encodeURIComponent(findingId)}${subscriptionQuery(subscription)}`,
 {method:"PUT",body:JSON.stringify({collected_at:collectedAt})},
);
export const getAzureMonitoringSchedule=id=>fetchRequest(`/azure/monitoring/schedule${subscriptionQuery(id)}`);
export const updateAzureMonitoringSchedule=(id,data)=>request(`/azure/monitoring/schedule${subscriptionQuery(id)}`,{method:"PUT",body:JSON.stringify(data)});
export const getAzureNetwork=id=>fetchRequest(`/azure/network${subscriptionQuery(id)}`);
export const refreshAzureNetwork=id=>request(`/azure/network/refresh${subscriptionQuery(id)}`,{method:"POST"});
export const getAzureSecurity=id=>fetchRequest(`/azure/security${subscriptionQuery(id)}`);
export const refreshAzureSecurity=id=>request(`/azure/security/refresh${subscriptionQuery(id)}`,{method:"POST"});
export const updateAzureFindingTracking=(subscription,id,data)=>request(
 `/azure/security/findings/${encodeURIComponent(id)}/tracking${subscriptionQuery(subscription)}`,
 {method:"PUT",body:JSON.stringify(data)},
);
export const listAssessments=()=>fetchRequest("/assessments");
export const getAssessmentPortfolio=page=>fetchRequest(`/assessments/portfolio?page=${page}`);
export const createAssessment=data=>request("/assessments",{method:"POST",body:JSON.stringify(data)});
export const getAssessment=id=>fetchRequest(`/assessments/${encodeURIComponent(id)}`);
export const getAssessmentSlaPolicy=()=>fetchRequest("/assessments/sla-policy");
export const saveAssessmentSlaPolicy=data=>request("/assessments/sla-policy",{method:"PUT",body:JSON.stringify(data)});
export const recordAssessmentRiskAcceptance=(assessmentId,findingId,data)=>request(
 `/assessments/${encodeURIComponent(assessmentId)}/findings/${encodeURIComponent(findingId)}/risk-acceptance`,
 {method:"PUT",body:JSON.stringify(data)},
);
export const importAssessmentFindings=(id,data)=>request(`/assessments/${encodeURIComponent(id)}/findings/import`,{
 method:"POST",body:JSON.stringify(data),
});
export const updateAssessmentFinding=(id,findingId,data)=>request(
 `/assessments/${encodeURIComponent(id)}/findings/${encodeURIComponent(findingId)}`,
 {method:"PUT",body:JSON.stringify(data)},
);
export const discoverAzureResources=(id,data)=>request(`/architectures/${id}/discover-resources`,{method:"POST",body:JSON.stringify(data)});
export const getResourceMonitoring=(aid,rid,data={})=>request(`/architectures/${aid}/resources/${rid}/monitoring`,{method:"POST",body:JSON.stringify(data)});
export const getArchitectureMonitoringSummary=(aid,data={})=>request(`/architectures/${aid}/monitoring-summary`,{method:"POST",body:JSON.stringify(data)});
export const getMonitoringIncidentSummary=(aid,data={})=>request(`/architectures/${aid}/incident-summary`,{method:"POST",body:JSON.stringify(data)});
export const getMonitoringAlertSummary=(aid,data={})=>request(`/architectures/${aid}/alerts-summary`,{method:"POST",body:JSON.stringify(data)});
export const getUnusedResourceSummary=(aid,data={})=>request(`/architectures/${aid}/unused-resources`,{method:"POST",body:JSON.stringify(data)});
export const listMonitoringIncidents=(aid,subscriptionId="")=>request(`/architectures/${aid}/incidents${subscriptionId?`?subscription_id=${encodeURIComponent(subscriptionId)}`:""}`);
export const listMonitoringSubscriptions=()=>request("/monitoring/subscriptions");
export const discoverMonitoringSubscriptions=()=>request("/monitoring/subscriptions/available");
export const connectMonitoringSubscription=data=>request("/monitoring/subscriptions",{method:"POST",body:JSON.stringify(data)});
export const refreshMonitoringSubscription=id=>request(`/monitoring/subscriptions/${id}/refresh`,{method:"POST"});
export const getMonitoringMetrics=(id,hours=24,interval="PT1H")=>request(`/monitoring/subscriptions/${id}/metrics?hours=${hours}&interval=${encodeURIComponent(interval)}`);
export const updateMonitoringSubscriptionIncidentStatus=(sid,iid,data)=>request(`/monitoring/subscriptions/${sid}/incidents/${encodeURIComponent(iid)}/status`,{method:"PUT",body:JSON.stringify(data)});
export const getMonitoringIncidentDetail=(aid,iid)=>request(`/architectures/${aid}/incidents/${iid}`);
export const updateMonitoringIncidentStatus=(aid,iid,data)=>request(`/architectures/${aid}/incidents/${iid}/status`,{method:"PUT",body:JSON.stringify(data)});
export const getGovernanceComplianceSummary=(aid,data={})=>request(`/architectures/${aid}/governance-summary`,{method:"POST",body:JSON.stringify(data)});
export const getGovernanceSecuritySummary=(aid,data={})=>request(`/architectures/${aid}/security-summary`,{method:"POST",body:JSON.stringify(data)});
export const getArchitectureIntelligenceAnalysis=(aid,data={})=>request(`/architectures/${aid}/intelligence-analysis`,{method:"POST",body:JSON.stringify(data)});
export const getArchitectureExecutiveReport=(aid,data={})=>request(`/reports/architectures/${aid}/executive-summary`,{method:"POST",body:JSON.stringify(data)});
export const estimateArchitectureCost=(id,data={})=>request(`/architectures/${id}/cost-estimate`,{method:"POST",body:JSON.stringify(data)});
export const getArchitectureActualCost=(id,data={})=>request(`/architectures/${id}/actual-cost`,{method:"POST",body:JSON.stringify(data)});
export const getSettingsOverview=()=>request("/settings");
export const getAzureConnectionStatus=()=>request("/settings/azure/status");
export const updateProviderApiKey=(provider,data)=>request(`/settings/providers/${provider}`,{method:"PUT",body:JSON.stringify(data)});
export const clearProviderApiKey=provider=>request(`/settings/providers/${provider}`,{method:"DELETE"});
export const testProviderConnection=provider=>request(`/settings/providers/${provider}/test`,{method:"POST",body:JSON.stringify({})});
export const saveAzureCredentials=data=>request("/settings/azure/credentials",{method:"PUT",body:JSON.stringify(data)});
export const clearAzureCredentials=()=>request("/settings/azure/credentials",{method:"DELETE"});
export const testAzureIntegration=id=>request(`/settings/azure/test${subscriptionQuery(id)}`,{method:"POST",body:JSON.stringify({})});
export const listAzureSubscriptionInventory=()=>request("/settings/azure/subscriptions");
export const listCloudAccounts=()=>request("/settings/cloud-accounts");
export const getCloudAccountStatus=provider=>request(`/settings/cloud-accounts/${provider}/status`);
export const saveCloudAccountCredentials=(provider,data)=>request(`/settings/cloud-accounts/${provider}/credentials`,{method:"PUT",body:JSON.stringify(data)});
export const clearCloudAccountCredentials=provider=>request(`/settings/cloud-accounts/${provider}/credentials`,{method:"DELETE"});
export const testCloudAccountConnection=provider=>request(`/settings/cloud-accounts/${provider}/test`,{method:"POST",body:JSON.stringify({})});
