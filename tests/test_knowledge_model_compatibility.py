from app.knowledge.models import KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentRecord


def test_knowledge_document_uses_the_integration_mapper() -> None:
    assert KnowledgeDocument is KnowledgeDocumentRecord
    assert KnowledgeDocumentRecord.__table__.fullname == "knowledge.documents"
    assert KnowledgeChunk.__table__.fullname == "knowledge.chunks"
