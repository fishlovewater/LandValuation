# Case History and Knowledge AI Integration Design

## Goal

Integrate `feature/case-history` and `origin/feature/knowledgeai` into the local
`feature/integrate-valuation-review` branch while treating the integration
branch as the authority for application behavior, database fields, ORM models,
routes, dependencies, and Alembic history.

The integration includes each subsystem's production APIs, existing tests, and
existing development demo or test tooling. It does not add a new Knowledge AI
frontend.

## Integration strategy

Use selective source import rather than directly merging either source branch.

### Case History

- Import `app/history/**` from `feature/case-history`.
- Register its exported router in the integration branch's `app/api/router.py`.
- Keep its read-only production behavior and its opt-in development seed and
  test UI.
- Do not import Case History's alternate Valuation, Review, or migration files.

### Knowledge AI

- Import the Knowledge AI module, providers, tests, documentation, and local
  development entry point from `origin/feature/knowledgeai`.
- Merge its required settings, router registration, storage behavior, and
  dependencies into the corresponding integration-branch files by hand.
- Preserve all existing Auth, Valuation, Review, and AI Assistant routes and
  behavior.

## Data and schema authority

- The integration branch's Alembic chain remains unchanged and must retain one
  head.
- The integration branch's `KnowledgeDocumentRecord` remains the sole ORM
  mapper for `knowledge.documents`.
- Add a compatible `KnowledgeChunk` mapper for the existing
  `knowledge.chunks` table. Adapt Knowledge AI imports with an alias or explicit
  import changes instead of defining a second document-table mapper.
- Existing Valuation and Review models, fields, constraints, and write flows
  are not replaced or renamed.
- History and Knowledge AI consume existing case, document, Valuation, Review,
  and knowledge data through their documented read boundaries.
- MinIO records continue to store bucket names and object keys, never fixed
  localhost URLs or persistent presigned URLs.

## Shared-file resolution

- `app/api/router.py`: retain every integration route and add History and
  Knowledge routes.
- `app/core/config.py`: retain integration OCR, Textract, maps, and AI settings;
  add Knowledge provider settings and consolidate shared Bedrock fields.
- `app/knowledge/__init__.py` and `app/knowledge/models.py`: expose one
  integration-compatible document model plus chunk support.
- `app/main.py` and `app/storage/service.py`: apply only the behavior required
  by Knowledge AI without replacing integration startup or storage rules.
- `requirements.txt`: use one compatible `boto3` constraint and retain all
  integration report, PDF, and existing runtime packages while adding genuine
  Knowledge AI requirements.
- `.env.example`: add only missing Knowledge settings and preserve all current
  integration settings.

## Error and safety behavior

- History keeps role-based visibility and returns an explicit unavailable
  result when metadata exists but a MinIO object is missing.
- Knowledge AI keeps source, date, document-type, and permission filtering.
- Answers without sufficient verified source evidence remain unsupported or
  request clarification; the integration must not add fallback guessing.
- Development seeds remain opt-in and deterministic and must not run during
  normal application startup.

## Verification

1. Run the original Case History tests, including API permissions and test UI
   contract coverage.
2. Run the Knowledge AI provider, source-grounding, citation, permission, case
   context, router, and runtime extraction tests.
3. Run focused integration regressions for route registration, Auth,
   Valuation-to-Review handoff, and the existing Knowledge document write flow.
4. Validate that Alembic reports exactly the integration branch's single head.
5. Run the full automated test suite and report failures separately as newly
   introduced or pre-existing.
6. Start the integrated application and smoke-test the History test UI and the
   documented Knowledge AI Swagger/local-provider path. Only flows actually
   executed in a persistent environment may be reported as manually verified.

## Existing-work protection and completion

The integration worktree already contains untracked `.serena/` and
`app/review/MANUAL_INTEGRATION_TEST_GUIDE.md` items. They are outside this
integration scope and must remain untouched and uncommitted.

The work is complete when both subsystem boundaries are available from the
integration application, the integration schema and migrations remain
authoritative, focused and full-suite verification results are recorded, and
no unrelated worktree changes are included.
