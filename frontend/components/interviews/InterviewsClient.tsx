"use client";

import {useEffect, useMemo, useState} from "react";
import {apiGet, apiSend} from "@/lib/api";

type Question = {id: string; question: string; category: string; source: string; source_platform?: string; source_url?: string};
type Prep = {
  interview: {round?: number; interview_type?: string; scheduled_at?: string; status: string};
  application: {id: string; company: string; role?: string; status: string};
  likely_topics: string[];
  public_research_questions: Question[];
  ai_generated_questions: Question[];
  recommended_experiences: {experience_id: string; title: string; score: number; why: string}[];
};

export function InterviewsClient({copy}: {copy: Record<string, string>}) {
  const [prep, setPrep] = useState<Prep | null>(null);
  const [selectedQuestion, setSelectedQuestion] = useState<Question | null>(null);
  const [selectedExperience, setSelectedExperience] = useState("");
  const [answer, setAnswer] = useState<Record<string, string> | null>(null);
  const [feedback, setFeedback] = useState<Record<string, unknown> | null>(null);
  const [userAnswer, setUserAnswer] = useState("");

  useEffect(() => {
    apiGet<{id: string; application: {id: string; company: string}}[]>("/api/v1/interviews").then(async (items) => {
      const tencent = items.find((item) => item.application.company.includes("腾讯") || item.application.company.toLowerCase().includes("tencent")) ?? items[0];
      if (!tencent) return;
      const data = await apiSend<Prep>(`/api/v1/applications/${tencent.application.id}/interview-prep`, "POST");
      setPrep(data);
      const first = data.public_research_questions[1] ?? data.public_research_questions[0] ?? data.ai_generated_questions[0];
      setSelectedQuestion(first);
      setSelectedExperience(data.recommended_experiences[0]?.experience_id ?? "");
    });
  }, []);

  const allQuestions = useMemo(() => [...(prep?.public_research_questions ?? []), ...(prep?.ai_generated_questions ?? [])], [prep]);

  async function generate() {
    if (!selectedQuestion || !selectedExperience) return;
    setAnswer(await apiSend<Record<string, string>>(`/api/v1/interview/questions/${selectedQuestion.id}/answers`, "POST", {experience_id: selectedExperience}));
  }

  async function analyse() {
    if (!selectedQuestion) return;
    setFeedback(await apiSend<Record<string, unknown>>(`/api/v1/interview/questions/${selectedQuestion.id}/analyse-answer`, "POST", {answer: userAnswer}));
  }

  if (!prep) return <div className="rounded-lg border border-line bg-white p-8 text-center text-muted shadow-card">{copy.loading}</div>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold text-ink">{copy.title}</h1>
        <p className="mt-2 text-muted">{prep.application.company} · {prep.application.role}</p>
      </div>
      <section className="grid gap-4 md:grid-cols-4">
        <Info title={copy.round} text={`第 ${prep.interview.round ?? 1} 轮`} />
        <Info title={copy.type} text={prep.interview.interview_type ?? ""} />
        <Info title={copy.status} text={prep.interview.status} />
        <Info title={copy.date} text={prep.interview.scheduled_at?.slice(0, 10) ?? ""} />
      </section>
      <section className="rounded-lg border border-line bg-white p-5 shadow-card">
        <h2 className="text-lg font-semibold text-ink">{copy.topics}</h2>
        <p className="mt-3 text-sm text-muted">{prep.likely_topics.join(" · ")}</p>
      </section>
      <section className="grid gap-4 lg:grid-cols-[1fr_1fr]">
        <QuestionGroup title={copy.publicResearch} questions={prep.public_research_questions} selected={selectedQuestion?.id} onSelect={setSelectedQuestion} />
        <QuestionGroup title={copy.aiGenerated} questions={prep.ai_generated_questions} selected={selectedQuestion?.id} onSelect={setSelectedQuestion} />
      </section>
      <section className="rounded-lg border border-line bg-white p-5 shadow-card">
        <h2 className="text-lg font-semibold text-ink">{copy.recommendedExperiences}</h2>
        <select value={selectedExperience} onChange={(event) => setSelectedExperience(event.target.value)} className="mt-3 h-10 w-full rounded-md border border-line px-3 text-sm">
          {prep.recommended_experiences.map((item) => <option key={item.experience_id} value={item.experience_id}>{item.title} · {item.score}%</option>)}
        </select>
        {prep.recommended_experiences.map((item) => <p key={item.experience_id} className="mt-2 text-sm text-muted">{item.title}: {item.why}</p>)}
        <button onClick={generate} className="mt-4 rounded-md bg-brand px-4 py-2 text-sm font-medium text-white">{copy.generate}</button>
      </section>
      {answer && (
        <section className="grid gap-4 md:grid-cols-3">
          <Info title={copy.answer30s} text={answer.answer_30s} />
          <Info title={copy.answer1min} text={answer.answer_1min} />
          <Info title={copy.answer2min} text={answer.answer_2min} />
        </section>
      )}
      <section className="rounded-lg border border-line bg-white p-5 shadow-card">
        <h2 className="text-lg font-semibold text-ink">{copy.practice}</h2>
        <textarea value={userAnswer} onChange={(event) => setUserAnswer(event.target.value)} className="mt-3 min-h-28 w-full rounded-md border border-line p-3 text-sm" />
        <button onClick={analyse} className="mt-3 rounded-md border border-line px-4 py-2 text-sm hover:border-brand hover:text-brand">{copy.analyse}</button>
        {feedback && <pre className="mt-4 whitespace-pre-wrap rounded-md bg-paper p-3 text-sm text-muted">{JSON.stringify(feedback, null, 2)}</pre>}
      </section>
    </div>
  );
}

function QuestionGroup({title, questions, selected, onSelect}: {title: string; questions: Question[]; selected?: string; onSelect: (question: Question) => void}) {
  return (
    <section className="rounded-lg border border-line bg-white p-5 shadow-card">
      <h2 className="text-lg font-semibold text-ink">{title}</h2>
      <div className="mt-4 space-y-2">
        {questions.map((question) => (
          <button key={question.id} onClick={() => onSelect(question)} className={`w-full rounded-md border p-3 text-left text-sm ${selected === question.id ? "border-brand bg-skysoft" : "border-line"}`}>
            <span className="font-medium text-ink">{question.category}</span>
            <span className="ml-2 text-xs text-brand">{title}</span>
            <span className="mt-2 block text-muted">{question.question}</span>
            {question.source_platform && <span className="mt-2 block text-xs text-muted">{question.source_platform}</span>}
          </button>
        ))}
      </div>
    </section>
  );
}

function Info({title, text}: {title: string; text: string}) {
  return <div className="rounded-lg border border-line bg-white p-5 shadow-card"><div className="text-sm text-muted">{title}</div><div className="mt-2 whitespace-pre-wrap text-sm font-medium text-ink">{text}</div></div>;
}
