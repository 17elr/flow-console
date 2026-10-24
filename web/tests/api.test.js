import test from 'node:test'
import assert from 'node:assert/strict'
import { api, refreshCsrf } from '../src/api.js'

test('fetch sends credentials and CSRF for JSON and FormData and handles empty 204', async () => {
  const requests = []
  globalThis.fetch = async (path, options) => { requests.push({ path, options }); return path.endsWith('/csrf') ? new Response(JSON.stringify({ token: 'fixture-csrf' }), { status: 200 }) : new Response(null, { status: 204 }) }
  await refreshCsrf()
  assert.equal(await api('/api/update', { method: 'PATCH', body: { title: 'Facts' } }), null)
  assert.equal(requests[1].options.headers['X-CSRF-Token'], 'fixture-csrf')
  assert.equal(requests[1].options.credentials, 'same-origin')
  assert.equal(requests[1].options.body, '{"title":"Facts"}')
  const form = new FormData(); form.append('file', new Blob(['image']), 'fixture.png')
  await api('/api/upload', { method: 'POST', body: form })
  assert.equal(requests[2].options.body, form)
  assert.equal(requests[2].options.headers['Content-Type'], undefined)
})

test('structured field errors remain available and unsuccessful responses never resolve as success', async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({ code: 'VALIDATION', message: 'Price invalid', fieldErrors: { price: 'Positive decimal required' }, requestId: 'fixture' }), { status: 422 })
  await assert.rejects(api('/api/product', { method: 'POST', body: {} }), error => error.status === 422 && error.fields.price === 'Positive decimal required' && error.requestId === 'fixture')
})
