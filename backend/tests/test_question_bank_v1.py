from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.services import question_bank_service as module


class Db:
    def __init__(self, existing=None): self.existing=existing; self.added=[]; self.commits=0
    def scalar(self, statement): return self.existing
    def add(self, row):
        if row.id is None: row.id=uuid4()
        if row.times_seen is None: row.times_seen=1
        if row.is_favorite is None: row.is_favorite=False
        now=datetime.now(timezone.utc);row.created_at=now;row.updated_at=now
        self.added.append(row);self.existing=row
    def flush(self): pass
    def commit(self): self.commits+=1
    def delete(self,row): self.existing=None


def row(owner, question="Tell me about a conflict", answer="Original answer", category="Behavioral"):
    return module.InterviewQuestionBankItem(id=uuid4(),user_id=owner,question=question,
        normalized_question=module.normalize_question(question),answer=answer,category=category,
        times_seen=1,is_favorite=False,source="manual",seen_keys=[],
        created_at=datetime.now(timezone.utc),updated_at=datetime.now(timezone.utc))


def test_create_item_normalizes_and_tracks_without_content(monkeypatch):
    owner=uuid4();db=Db();events=[]
    monkeypatch.setattr(module,"track_event",lambda **kw:events.append(kw))
    result=module.question_bank_service.save(db,owner,question="  Tell   Me About A Conflict  ",answer="Private answer",category="Behavioral")
    assert db.added[0].normalized_question=="tell me about a conflict" and result["times_seen"]==1
    assert "normalized_question" not in result and "seen_keys" not in result
    assert events[0]["event_name"]=="question_bank_item_created"
    assert "Private answer" not in repr(events) and "Tell" not in repr(events)


def test_duplicate_increments_seen_and_never_overwrites_answer(monkeypatch):
    owner=uuid4();existing=row(owner);db=Db(existing);events=[]
    monkeypatch.setattr(module,"track_event",lambda **kw:events.append(kw))
    result=module.question_bank_service.save(db,owner,question=" tell me ABOUT a conflict ",answer="New answer")
    assert result["duplicate"] and result["answer_conflict"] and result["times_seen"]==2
    assert existing.answer=="Original answer" and events[0]["event_name"]=="question_bank_item_seen_again"


def test_actual_interview_occurrence_is_idempotent(monkeypatch):
    owner=uuid4();existing=row(owner);db=Db(existing);monkeypatch.setattr(module,"track_event",lambda **kw:None)
    first=module.question_bank_service.save(db,owner,question=existing.question,source="actual_interview",occurrence_key="request-1:q")
    second=module.question_bank_service.save(db,owner,question=existing.question,source="actual_interview",occurrence_key="request-1:q")
    assert first["times_seen_incremented"] and not second["times_seen_incremented"] and existing.times_seen==2


def test_owned_get_update_favorite_delete(monkeypatch):
    owner,other=uuid4(),uuid4();item=row(owner);db=Db(item);events=[]
    monkeypatch.setattr(module,"track_event",lambda **kw:events.append(kw))
    monkeypatch.setattr(module.question_bank_service,"get",lambda db,user,item_id:item if user==owner and item_id==item.id else None)
    assert module.question_bank_service.update(db,other,item.id,{"answer":"stolen"}) is None
    assert module.question_bank_service.favorite(db,other,item.id,True) is None
    assert not module.question_bank_service.delete(db,other,item.id)
    db.existing=None
    assert module.question_bank_service.update(db,owner,item.id,{"answer":"Edited","category":"Product"})["answer"]=="Edited"
    assert module.question_bank_service.favorite(db,owner,item.id,True)["is_favorite"]
    assert module.question_bank_service.delete(db,owner,item.id)
    assert [event["event_name"] for event in events]==["question_bank_item_updated","question_bank_item_favorited","question_bank_item_deleted"]


def test_normalization_is_stable():
    assert module.normalize_question("  WHY   this Role?\n") == "why this role?"


def test_search_category_and_favorite_filters_are_owner_scoped():
    owner=uuid4();captured=[]
    class Result:
        def all(self): return []
    class SearchDb:
        def scalars(self,statement): captured.append(str(statement));return Result()
    assert module.question_bank_service.list(SearchDb(),owner,"roadmap","Product",True)==[]
    sql=captured[0]
    assert "user_id" in sql and "lower" in sql and "category" in sql and "is_favorite" in sql
    assert "times_seen DESC" in sql and "updated_at DESC" in sql
