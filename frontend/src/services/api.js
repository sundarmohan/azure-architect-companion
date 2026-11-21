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
 const method=(options.method||"GET").toUpperCase();
 const headers=new Headers(options.headers);
 if(options.body) headers.set("Content-Type","application/json");
 if(method!=="GET") headers.set("X-MonitorAI-Request","1");
 if(clientId&&!authRoute) headers.set("X-Client-ID",clientId);
 const r=await fetch(`${API}${path}`,{...options,headers,credentials:"include"});
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
 const data=r.status===204?null:await r.json();
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
export const getCurrentUser=()=>fetchRequest("/auth/me",{cache:"no-store"});
export const changePassword=data=>authWrite("password",data);
export const createUser=data=>authWrite("users",data);
export const resetUserPassword=(username,data)=>authWrite(`users/${encodeURIComponent(username)}/password`,data);
export const createClient=data=>authWrite("clients",data);
export const setClientMember=(id,data)=>authWrite(`clients/${encodeURIComponent(id)}/members`,data);
export const listArchitectures=()=>request("/architectures");
export const createArchitecture=data=>request("/architectures",{method:"POST",body:JSON.stringify(data)});
export const updateArchitecture=(id,data)=>request(`/architectures/${id}`,{method:"PUT",body:JSON.stringify(data)});
export const deleteArchitecture=id=>request(`/architectures/${id}`,{method:"DELETE"});
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
export const testAzureIntegration=()=>request("/settings/azure/test",{method:"POST",body:JSON.stringify({})});
export const listAzureSubscriptionInventory=()=>request("/settings/azure/subscriptions");
export const listCloudAccounts=()=>request("/settings/cloud-accounts");
export const getCloudAccountStatus=provider=>request(`/settings/cloud-accounts/${provider}/status`);
export const saveCloudAccountCredentials=(provider,data)=>request(`/settings/cloud-accounts/${provider}/credentials`,{method:"PUT",body:JSON.stringify(data)});
export const clearCloudAccountCredentials=provider=>request(`/settings/cloud-accounts/${provider}/credentials`,{method:"DELETE"});
export const testCloudAccountConnection=provider=>request(`/settings/cloud-accounts/${provider}/test`,{method:"POST",body:JSON.stringify({})});
