import { useState } from "react";
import { apiPost } from "../lib/api";
import { Badge, Card } from "../components/ui/Card";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { useApi } from "../hooks/useApi";
import { AlertIcon, BulbIcon, InfoIcon, RefreshIcon } from "../components/icons";
import { formatCurrency, formatDate } from "../lib/format";
import {
  changeHint,
  severityLabel,
  sortInsights,
  sourceLabel,
  sourceTone,
} from "../lib/assistant";
import type {
  AssistantAskRequest,
  AssistantAskResponse,
  AssistantInsight,
  AssistantOverviewResponse,
} from "../types/api";
import styles from "./Assistant.module.css";

function metricValue(insight: AssistantInsight, currency: string): string | null {
  const m = insight.metric;
  if (!m || m.current === null) return null;
  if (m.unit === "currency") return formatCurrency(m.current, currency);
  if (m.unit === "percent") return `${m.current}%`;
  if (m.unit === "months") return `~${m.current} months`;
  return String(m.current);
}

function InsightCard({ insight, currency }: { insight: AssistantInsight; currency: string }) {
  const value = metricValue(insight, currency);
  return (
    <article className={`${styles.insight} ${styles[`tone-${insight.severity}`] ?? ""}`}>
      <div className={styles.insightHead}>
        <Badge tone={insight.severity === "critical" ? "negative" : insight.severity === "warning" ? "warning" : insight.severity === "success" ? "positive" : "neutral"}>
          {severityLabel(insight.severity)}
        </Badge>
        <span className={styles.insightCategory}>{insight.category}</span>
        {insight.actionable && <Badge tone="accent">actionable</Badge>}
      </div>
      <h3 className={styles.insightTitle}>{insight.title}</h3>
      <p className={styles.insightExplanation}>{insight.explanation}</p>
      {insight.metric && (
        <dl className={styles.metricRow}>
          {insight.metric.label && <dt>{insight.metric.label}</dt>}
          {value && <dd className="num">{value}</dd>}
          {insight.metric.change_pct !== null && insight.metric.change_pct !== undefined && (
            <dd className={styles.metricHint}>{changeHint(insight.metric.change_pct)}</dd>
          )}
        </dl>
      )}
    </article>
  );
}

function AskBox({ questions, currency }: { questions: AssistantOverviewResponse["questions"]; currency: string }) {
  const [draft, setDraft] = useState("");
  const [answer, setAnswer] = useState<AssistantAskResponse | null>(null);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(payload: AssistantAskRequest) {
    setAsking(true);
    setError(null);
    try {
      const result = await apiPost<AssistantAskResponse>("/assistant/ask", payload);
      setAnswer(result);
      setDraft("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error");
    } finally {
      setAsking(false);
    }
  }

  function onChip(question: string) {
    submit({ question });
  }

  return (
    <div className={styles.askWrap}>
      <form
        className={styles.askForm}
        onSubmit={(event) => {
          event.preventDefault();
          if (!draft.trim() || asking) return;
          void submit({ question: draft.trim() });
        }}
      >
        <label className={styles.askLabel} htmlFor="assistant-question">
          Ask about your money
        </label>
        <div className={styles.askRow}>
          <input
            id="assistant-question"
            className={styles.askInput}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="e.g. How much can I safely spend today?"
            disabled={asking}
          />
          <button type="submit" className={styles.askButton} disabled={asking || !draft.trim()}>
            {asking ? "Thinking…" : "Ask"}
          </button>
        </div>
      </form>

      {questions.length > 0 && (
        <div className={styles.chips} aria-label="Suggested questions">
          {questions.map((question) => (
            <button
              key={question.intent}
              type="button"
              className={styles.chip}
              onClick={() => onChip(question.question)}
              disabled={asking}
            >
              {question.question}
            </button>
          ))}
        </div>
      )}

      {error && <ErrorState title="Could not answer" message={error} />}

      {answer && (
        <Card title={answer.question} subtitle={sourceLabel(answer.source)} className={styles.answerCard}>
          {answer.recognized ? (
            <>
              <div className={styles.answerText}>{answer.answer}</div>
              <div className={styles.answerMeta}>
                <Badge tone={sourceTone(answer.source)}>{sourceLabel(answer.source)}</Badge>
                {answer.estimate && <Badge tone="warning">estimate</Badge>}
                {answer.metric && answer.metric.current !== null && (
                  <span className={`num ${styles.answerMetric}`}>
                    {answer.metric.unit === "currency"
                      ? formatCurrency(answer.metric.current, currency)
                      : answer.metric.unit === "percent"
                        ? `${answer.metric.current}%`
                        : String(answer.metric.current)}
                  </span>
                )}
              </div>
              {answer.facts.length > 0 && (
                <dl className={styles.facts}>
                  {answer.facts.map((fact) => (
                    <div key={fact.label} className={styles.fact}>
                      <dt>{fact.label}</dt>
                      <dd className="num">{fact.display}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </>
          ) : (
            <EmptyState icon={<InfoIcon size={18} />} title="Not quite" description={answer.answer} />
          )}
        </Card>
      )}
    </div>
  );
}

export function AssistantPage() {
  const overview = useApi<AssistantOverviewResponse>("/assistant");
  const data = overview.data;
  const currency = data?.currency ?? "EUR";
  const insights = sortInsights(data?.insights ?? []);
  const periodLabel = data
    ? `${formatDate(data.period.period_start)} – ${formatDate(data.period.period_end)}`
    : "";

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-header__eyebrow">Insights</div>
          <h1>Financial Assistant</h1>
          <p className="page-header__subtitle">
            {periodLabel || "Your money, explained"}
            {data ? ` · ${data.provider_name}` : ""}
          </p>
        </div>
        <div className={styles.headerBadges}>
          <Badge tone={data?.has_data ? "accent" : "neutral"}>
            {data?.has_data ? "From your ledger" : "Empty ledger"}
          </Badge>
        </div>
      </div>

      {overview.error && (
        <ErrorState title="Cannot load the assistant" message={overview.error} onRetry={overview.reload} />
      )}

      {!overview.error && !data && (
        <Card title="Financial Assistant" bodyClassName={styles.loading}>
          <LoadingState label="Reading your ledger…" />
        </Card>
      )}

      {data && (
        <div className={styles.layout}>
          <div className={styles.span7}>
            <Card
              title={data.greeting}
              subtitle="Deterministic insights computed from your actual recorded finances"
              action={
                <button type="button" className={styles.refresh} onClick={overview.reload} aria-label="Refresh">
                  <RefreshIcon size={15} />
                </button>
              }
            >
{data.has_data ? (
            <p className={styles.overview}>{data.overview}</p>
          ) : (
            <EmptyState
              icon={<BulbIcon size={20} />}
              title="Nothing to analyze yet"
              description="Record or import transactions first — the assistant only describes what is actually in your ledger."
            />
          )}
        </Card>
      </div>
          <div className={styles.span5}>
            <AskBox questions={data.questions} currency={currency} />
          </div>
        </div>
      )}

      {data && (
        <>
          <div className="section-title">
            <h2>What I noticed</h2>
            <span>{insights.length} prioritized insight{insights.length === 1 ? "" : "s"}</span>
          </div>

          {insights.length === 0 ? (
            <Card>
              <EmptyState
                icon={<BulbIcon size={20} />}
                title="Nothing noteworthy this period"
                description="When something deterministic crosses a threshold (budget, savings rate, obligations), it shows up here."
              />
            </Card>
          ) : (
            <div className={styles.insightGrid}>
              {insights.map((insight) => (
                <InsightCard key={insight.id} insight={insight} currency={currency} />
              ))}
            </div>
          )}

          <Card className={styles.safetyNote}>
            <div className={styles.safetyNoteIcon}>
              <AlertIcon size={18} />
            </div>
            <div>
              <h3>How this assistant works</h3>
              <p>
                Every figure comes from your ledger. Estimates are labeled as such and never
                presented as certainties; the assistant does not access your bank.
              </p>
            </div>
          </Card>
        </>
      )}
    </>
  );
}