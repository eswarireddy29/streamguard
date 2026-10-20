/**
 * src/api.js
 *
 * One place that talks to the FastAPI service.
 *
 * WHY A CLIENT MODULE RATHER THAN fetch() IN COMPONENTS:
 *  - the bearer token is attached in exactly one place, so no
 *    component can forget it
 *  - a 401 is handled once: clear the token and let the app show the
 *    login screen, rather than each component inventing its own
 *    behaviour
 *  - every call goes through /api, which the Vite proxy forwards, so
 *    no component hardcodes a host
 */

const BASE = '/api'
const TOKEN_KEY = 'streamguard_token'
const ROLE_KEY = 'streamguard_role'
const USER_KEY = 'streamguard_user'

// ---------------------------------------------------------------
//  Token storage
// ---------------------------------------------------------------
// sessionStorage, not localStorage: the token dies when the tab
// closes. A fraud console left open on a shared machine should not
// hand the next person a valid session.

export function getToken() {
  try {
    return sessionStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function getRole() {
  try {
    return sessionStorage.getItem(ROLE_KEY)
  } catch {
    return null
  }
}

export function getUsername() {
  try {
    return sessionStorage.getItem(USER_KEY)
  } catch {
    return null
  }
}

function setSession(token, role, username) {
  try {
    sessionStorage.setItem(TOKEN_KEY, token)
    sessionStorage.setItem(ROLE_KEY, role || '')
    sessionStorage.setItem(USER_KEY, username || '')
  } catch {
    /* private browsing - the app still works for this tab */
  }
}

export function clearSession() {
  try {
    sessionStorage.removeItem(TOKEN_KEY)
    sessionStorage.removeItem(ROLE_KEY)
    sessionStorage.removeItem(USER_KEY)
  } catch {
    /* ignore */
  }
}

// ---------------------------------------------------------------
//  The request wrapper
// ---------------------------------------------------------------

export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === 'string' ? detail : JSON.stringify(detail))
    this.status = status
    this.detail = detail
  }
}

async function request(path, { method = 'GET', body, auth = true } = {}) {
  const headers = { 'Content-Type': 'application/json' }

  if (auth) {
    const token = getToken()
    if (token) headers.Authorization = `Bearer ${token}`
  }

  let response
  try {
    response = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch (err) {
    // The API is not reachable at all - a different problem from a
    // rejected request, and worth saying so plainly.
    throw new ApiError(0, 'Cannot reach the scoring service. Is it running?')
  }

  if (response.status === 401) {
    // The token is missing, invalid or expired. Clearing it here means
    // the app falls back to the login screen without every component
    // having to think about it.
    clearSession()
    throw new ApiError(401, 'Session expired. Please sign in again.')
  }

  const text = await response.text()
  const data = text ? JSON.parse(text) : null

  if (!response.ok) {
    throw new ApiError(response.status, data?.detail ?? response.statusText)
  }

  return data
}

// ---------------------------------------------------------------
//  Endpoints
// ---------------------------------------------------------------

export async function login(username, password) {
  const data = await request('/auth/token', {
    method: 'POST',
    body: { username, password },
    auth: false,
  })
  setSession(data.access_token, data.role, username)
  return data
}

export function whoami() {
  return request('/auth/me')
}

export function health() {
  // /health is deliberately unauthenticated - a load balancer needs it.
  return request('/health', { auth: false })
}

export function listCases({ limit = 50, status = 'open', assignedTo } = {}) {
  const params = new URLSearchParams({ limit: String(limit), status })
  if (assignedTo) params.set('assigned_to', assignedTo)
  return request(`/cases?${params}`)
}

export function getCase(caseRef) {
  return request(`/cases/${encodeURIComponent(caseRef)}`)
}

export function assignCase(caseRef) {
  // No analyst name: the server takes the identity from the token.
  return request(`/cases/${encodeURIComponent(caseRef)}/assign`, {
    method: 'POST',
    body: {},
  })
}

export function submitVerdict(caseRef, verdict, notes = '') {
  return request(`/cases/${encodeURIComponent(caseRef)}/verdict`, {
    method: 'POST',
    body: { verdict, notes },
  })
}

export function caseStats() {
  return request('/cases-stats')
}

export function scoreTransaction(payload) {
  return request('/score', { method: 'POST', body: payload })
}

// ---------------------------------------------------------------
//  Permissions, mirroring the server
// ---------------------------------------------------------------
// This hides controls a role cannot use. It is NOT a security
// boundary - the server enforces permissions and returns 403. Anyone
// can edit JavaScript in their own browser; the point here is to
// avoid showing a button that will fail.

const PERMISSIONS = {
  service: ['score'],
  analyst: ['score', 'read_cases', 'assign_case', 'submit_verdict'],
  risk_manager: [
    'score', 'read_cases', 'assign_case', 'submit_verdict',
    'manage_policy', 'read_stats',
  ],
}

export function can(permission, role = getRole()) {
  return (PERMISSIONS[role] || []).includes(permission)
}

export function recentDecisions({ limit = 50, sinceId = 0 } = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    since_id: String(sinceId),
  })
  return request(`/recent-decisions?${params}`)
}

export function riskKpis({ fnCost, fpCost } = {}) {
  const params = new URLSearchParams()
  if (fnCost) params.set('fn_cost', String(fnCost))
  if (fpCost) params.set('fp_cost', String(fpCost))
  const q = params.toString()
  return request(`/risk-kpis${q ? `?${q}` : ''}`)
}
