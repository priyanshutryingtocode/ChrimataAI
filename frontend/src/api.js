const API_BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "")

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`
  const response = await fetch(url, options)
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      if (body?.detail) {
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
      }
    } catch {
      /* keep default detail */
    }
    throw new Error(detail)
  }
  return response.json()
}

export function listBatches() {
  return request('/api/batches')
}

export function getBatch(id) {
  return request(`/api/batches/${id}`)
}

export function getMetrics(id) {
  return request(`/api/batches/${id}/metrics`)
}

export function reconcileBatch(id) {
  return request(`/api/batches/${id}/reconcile`, { method: 'POST' })
}

export function uploadBatch({ name, orders, payments, settlements, refunds, groundTruth }) {
  const form = new FormData()
  if (name) form.append('name', name)
  const mapping = [
    ['orders', orders],
    ['payments', payments],
    ['settlements', settlements],
    ['refunds', refunds],
    ['ground_truth', groundTruth],
  ]
  for (const [field, file] of mapping) {
    if (file) form.append(field, file)
  }
  return request('/api/batches/upload', { method: 'POST', body: form })
}

export function getResults(id, { status, limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (status) params.set('status', status)
  return request(`/api/batches/${id}/results?${params.toString()}`)
}

export function getExceptions(id, { exceptionType, limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (exceptionType) params.set('exception_type', exceptionType)
  return request(`/api/batches/${id}/exceptions?${params.toString()}`)
}

export function controllerQuery(batchId, question) {
  return request('/api/controller/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ batch_id: batchId, question }),
  })
}

export function getEvidence(batchId, transactionId) {
  return request(`/api/batches/${batchId}/exceptions/${transactionId}/evidence`)
}

export function createProposal(batchId, transactionId, useLlm = true) {
  return request(`/api/batches/${batchId}/exceptions/${transactionId}/proposal`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ use_llm: useLlm }),
  })
}

export function decideResolution(batchId, transactionId, { decision, approvedAmount, approvedBy, note }) {
  const payload = { decision, approved_by: approvedBy || 'dashboard-user', note: note || '' }
  if (approvedAmount !== null && approvedAmount !== undefined && approvedAmount !== '') {
    payload.approved_amount = Number(approvedAmount)
  }
  return request(`/api/batches/${batchId}/exceptions/${transactionId}/resolution`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function listResolutions(batchId, { status, transactionId, limit = 200 } = {}) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (status) params.set('status', status)
  if (transactionId) params.set('transaction_id', transactionId)
  return request(`/api/batches/${batchId}/resolutions?${params.toString()}`)
}
