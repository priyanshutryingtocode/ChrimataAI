async function request(path, options = {}) {
  const response = await fetch(path, options)
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
