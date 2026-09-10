import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { DEMO_REQUIRED_CAPABILITIES } from '../../src/types/capability'

const artifact = JSON.parse(
  readFileSync(
    resolve(process.cwd(), 'docs/openapi-target.json'),
    'utf8',
  ),
)

describe('demo capability boundary', () => {
  it('requires one real flow per subsystem', () => {
    expect(DEMO_REQUIRED_CAPABILITIES).toEqual({
      auth: true,
      valuation: true,
      review: true,
      history: true,
      assistant: true,
    })
  })

  it('freezes the source-derived cited Assistant contract', () => {
    const assistantPaths = artifact.paths
    const assistantOperation = (path: string, method: 'get' | 'post') => {
      const pathItem = assistantPaths[path]
      expect(pathItem).toBeDefined()
      const operation = pathItem?.[method]
      expect(operation).toBeDefined()
      return operation
    }
    const assistantOperations = [
      assistantOperation('/api/v1/ai-assistant/sessions', 'post'),
      assistantOperation('/api/v1/ai-assistant/sessions/{session_id}', 'get'),
      assistantOperation('/api/v1/ai-assistant/sessions/{session_id}/progress', 'get'),
      assistantOperation('/api/v1/ai-assistant/sessions/{session_id}/messages', 'post'),
      assistantOperation('/api/v1/ai-assistant/sessions/{session_id}/questions', 'post'),
    ]
    assistantOperations.forEach((operation) => {
      expect(operation.security).toEqual([{ HTTPBearer: [] }])
    })
    expect(
      assistantPaths['/api/v1/ai-assistant/sessions/{session_id}/questions'].post
        .requestBody.content['application/json'].schema,
    ).toEqual({ $ref: '#/components/schemas/AssistantQuestionRequest' })
    expect(
      assistantPaths['/api/v1/ai-assistant/sessions/{session_id}/questions'].post
        .responses['200'].content['application/json'].schema,
    ).toEqual({ $ref: '#/components/schemas/AssistantQuestionResponse' })
    expect(
      assistantPaths['/api/v1/ai-assistant/sessions/{session_id}/messages'].post
        .requestBody.content['application/json'].schema,
    ).toEqual({ $ref: '#/components/schemas/AssistantMessageRequest' })
    expect(
      assistantPaths['/api/v1/ai-assistant/sessions/{session_id}/messages'].post
        .responses['200'].content['application/json'].schema,
    ).toEqual({ $ref: '#/components/schemas/AssistantMessageResponse' })

    const schemaShape = (name: string) => ({
      properties: Object.keys(artifact.components.schemas[name].properties).sort(),
      required: [...(artifact.components.schemas[name].required ?? [])].sort(),
    })
    expect(schemaShape('AssistantQuestionRequest')).toEqual({
      properties: ['as_of_date', 'document_types', 'limit', 'question'],
      required: ['question'],
    })
    expect(schemaShape('AssistantQuestionResponse')).toEqual({
      properties: [
        'answer',
        'answer_status',
        'assistant_session_id',
        'citations',
        'claims',
        'clarification_question',
        'generation_mode',
        'next_action',
        'unreadable_sources',
      ],
      required: [
        'answer',
        'answer_status',
        'assistant_session_id',
        'generation_mode',
        'next_action',
      ],
    })
    expect(schemaShape('AssistantClaim')).toEqual({
      properties: ['citation_ids', 'text'],
      required: ['citation_ids', 'text'],
    })
    expect(schemaShape('AssistantCitation')).toEqual({
      properties: [
        'article_no',
        'citation_id',
        'document_code',
        'document_id',
        'document_title',
        'effective_from',
        'effective_to',
        'page_end',
        'page_start',
        'quoted_text',
        'section_title',
        'supported_claim',
        'supporting_quote',
        'version_no',
      ],
      required: [
        'article_no',
        'citation_id',
        'document_code',
        'document_id',
        'document_title',
        'effective_from',
        'effective_to',
        'page_end',
        'page_start',
        'quoted_text',
        'section_title',
        'version_no',
      ],
    })
    expect(schemaShape('AssistantMessageRequest')).toEqual({
      properties: [
        'confirm_action',
        'confirm_apply',
        'confirmed_candidate_ids',
        'confirmed_fields',
        'content',
        'generate_report_pdf',
        'nearest_facility',
        'run_calculation',
        'run_validation',
      ],
      required: ['content'],
    })
    expect(schemaShape('AssistantMessageResponse')).toEqual({
      properties: ['progress', 'reply', 'session', 'tools'],
      required: ['progress', 'reply', 'session', 'tools'],
    })
    expect(artifact['x-target-provenance']).toMatchObject({
      sourceBranch: 'codex/frontend-demo',
      sourceCommit: 'f3bb8d02c4f95e671d39010e51baf0226c2ae0ef',
      scopedPathCount: 38,
      scopedOperationCount: 39,
      scopedSchemaCount: 83,
    })
    expect(artifact.components.securitySchemes).toEqual({
      HTTPBearer: { type: 'http', scheme: 'bearer' },
    })
    expect(Object.keys(artifact.paths)).not.toEqual(
      expect.arrayContaining([
        '/api/v1/knowledge/search',
        '/api/v1/knowledge/ask',
        '/api/v1/valuation/automation/workflows',
      ]),
    )

    const refs: string[] = []
    const collectRefs = (value: unknown, target: string[] = refs): void => {
      if (!value || typeof value !== 'object') return
      if (Array.isArray(value)) {
        value.forEach((nested) => collectRefs(nested, target))
        return
      }
      Object.entries(value).forEach(([key, nested]) => {
        if (key === '$ref' && typeof nested === 'string') target.push(nested)
        else collectRefs(nested, target)
      })
    }
    collectRefs(artifact.paths)
    const pending = [...new Set(refs)]
    const visited = new Set<string>()
    while (pending.length) {
      const ref = pending.shift() as string
      if (!ref.startsWith('#/components/schemas/') || visited.has(ref)) continue
      visited.add(ref)
      const name = ref.slice('#/components/schemas/'.length)
      const schema = artifact.components.schemas[name]
      expect(schema).toBeDefined()
      const nestedRefs: string[] = []
      collectRefs(schema, nestedRefs)
      nestedRefs.forEach((nestedRef) => pending.push(nestedRef))
    }
  })
})
