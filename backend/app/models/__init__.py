"""Central import point so every model is registered on Base's mapper
registry before relationships (declared as string forward-refs) are
resolved. Import `app.models` once at startup (main.py does this) before
using the ORM.
"""
from app.models.conversation import AgentMode, Conversation, Message, MessageRole  # noqa: F401
from app.models.document import Document, DocumentFormat, DocumentStatus  # noqa: F401
from app.models.history import HistoryEntry, HistoryEntryStatus, HistoryEntryType  # noqa: F401
from app.models.knowledge_analysis import KnowledgeAnalysis, KnowledgeAnalysisStatus  # noqa: F401
from app.models.project import Project, ProjectStatus  # noqa: F401
from app.models.session import UserSession  # noqa: F401
from app.models.token import EmailVerificationToken, PasswordResetToken  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.user_settings import UserSettings  # noqa: F401

__all__ = [
    "User",
    "UserSession",
    "UserSettings",
    "EmailVerificationToken",
    "PasswordResetToken",
    "Project",
    "ProjectStatus",
    "HistoryEntry",
    "HistoryEntryType",
    "HistoryEntryStatus",
    "Conversation",
    "Message",
    "AgentMode",
    "MessageRole",
    "KnowledgeAnalysis",
    "KnowledgeAnalysisStatus",
    "Document",
    "DocumentFormat",
    "DocumentStatus",
]
