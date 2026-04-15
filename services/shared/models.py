"""Shared data models for inter-service communication"""
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional
from datetime import datetime

class JobStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    COMPLETED = "completed"
    FAILED = "failed"
    CACHED = "cached"

class ErrorType(str, Enum):
    BLOCKED = "blocked"
    RATE_LIMITED = "rate_limited"
    PRIVATE = "private"
    DELETED = "deleted"
    INVALID_URL = "invalid_url"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"

@dataclass
class Job:
    job_id: str
    link: str
    user_id: Optional[str]
    status: JobStatus = JobStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    error_type: Optional[ErrorType] = None
    created_at: str = None
    updated_at: str = None
    
    def to_dict(self):
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data):
        return cls(**data)

@dataclass
class TranscribeRequest:
    link: str
    user_id: Optional[str] = None
    service: str = "deepgram"
    
    def to_dict(self):
        return asdict(self)

@dataclass
class TranscribeResponse:
    success: bool
    job_id: str
    status: JobStatus
    transcript: Optional[str] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    queue_position: Optional[int] = None
    
    def to_dict(self):
        return asdict(self)
