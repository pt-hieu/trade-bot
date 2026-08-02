"use client"

import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useCompanyResearch } from '../../hooks/use-watchlist'
import { ReviewFlags } from './review-flags'
import { Skeleton } from '../ui/skeleton'
import { ErrorState } from '../ui/error-state'
import { cn } from '../../lib/utils'
import { formatPriceVnd } from '../../lib/watchlist-utils'
import type { EntryProximity } from '../../lib/watchlist-utils'
import { AlertTriangle, Bot, Calendar, ChevronRight } from 'lucide-react'
import type { ResearchSectionKey } from '../../types/index'

// ─── Signal Extraction ──────────────────────────────────────────────────────

function stripMarkdown(text: string): string {
  return text
    .replace(/#{1,6}\s+/g, '')
    .replace(/\*{1,2}([^*]+)\*{1,2}/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .trim()
}

function extractVerdict(thesis: string): string {
  const clean = stripMarkdown(thesis)
  const sentenceEnd = clean.search(/[.!?](\s|$)/)
  if (sentenceEnd > 0 && sentenceEnd < 120) return clean.slice(0, sentenceEnd + 1)
  return clean.slice(0, 100) + (clean.length > 100 ? '…' : '')
}

function extractSignal(content: string): { value: string; detail: string } {
  const lines = stripMarkdown(content).split('\n').filter((line) => line.trim())
  return {
    value: (lines[0] ?? '').slice(0, 80),
    detail: (lines[1] ?? '').slice(0, 140),
  }
}

function extractRiskItems(content: string): string[] {
  const clean = stripMarkdown(content)
  const listItems = clean.split('\n')
    .map((line) => line.trim())
    .filter((line) => /^[-*•]\s|^\d+[.)]\s/.test(line))
    .map((line) => line.replace(/^[-*•]\s+|^\d+[.)]\s+/, '').trim())
  if (listItems.length > 0) return listItems.slice(0, 5)
  return clean.split(/[.!?]\s+/).filter((sentence) => sentence.length > 15).slice(0, 5)
}

const SIGNAL_SECTIONS: { key: ResearchSectionKey; label: string }[] = [
  { key: 'valuation', label: 'Valuation' },
  { key: 'moat', label: 'Moat Quality' },
  { key: 'growth', label: 'Growth' },
  { key: 'financials', label: 'Financials' },
]

const PROSE_SECTIONS: ResearchSectionKey[] = [
  'overview', 'moat', 'growth', 'valuation', 'financials', 'management',
]

const SECTION_LABEL: Partial<Record<ResearchSectionKey, string>> = {
  thesis: 'Investment Thesis', overview: 'Overview', moat: 'Competitive Moat',
  growth: 'Growth Outlook', valuation: 'Valuation', financials: 'Financials',
  management: 'Management', risks: 'Risks',
}

const RISK_INTENSITY = ['bg-rose-500/12', 'bg-rose-500/8', 'bg-rose-500/6', 'bg-rose-500/4', 'bg-rose-500/3']

// ─── Component ──────────────────────────────────────────────────────────────

interface ResearchPanelProps {
  ticker: string
  reviewFlags?: string[]
  entryZoneVnd?: number | null
  entryProximity?: EntryProximity | null
}

export function ResearchPanel({
  ticker, reviewFlags = [], entryZoneVnd, entryProximity,
}: ResearchPanelProps) {
  const { data: research, isLoading, error, refetch } = useCompanyResearch(ticker)
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set())

  const toggleSection = (key: string) => {
    setExpandedSections((previous) => {
      const next = new Set(previous)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        {reviewFlags.length > 0 && <ReviewFlags flags={reviewFlags} />}
        <Skeleton className="h-12 w-full" />
        <div className="grid grid-cols-2 gap-2"><Skeleton className="h-16" /><Skeleton className="h-16" /></div>
      </div>
    )
  }
  if (error) {
    return (
      <div className="space-y-2">
        {reviewFlags.length > 0 && <ReviewFlags flags={reviewFlags} />}
        <ErrorState description="Could not load research." retry={refetch} />
      </div>
    )
  }
  if (!research) {
    return (
      <div className="space-y-2">
        {reviewFlags.length > 0 && <ReviewFlags flags={reviewFlags} />}
        <p className="text-sm text-muted-foreground italic">No research available.</p>
      </div>
    )
  }

  const thesis = research.sections.thesis
  const verdict = thesis ? extractVerdict(thesis) : null
  const riskItems = extractRiskItems(research.sections.risks ?? '')
  const signalCards = SIGNAL_SECTIONS
    .filter((section) => research.sections[section.key])
    .map((section) => ({ ...section, ...extractSignal(research.sections[section.key]!) }))
  const proseSections = PROSE_SECTIONS.filter((key) => research.sections[key])

  return (
    <div className="space-y-4 animate-in fade-in slide-in-from-top-1 duration-200">
      {/* ── Level 1: Verdict Bar ──────────────────────────────────── */}
      {verdict && (
        <div className="flex items-center justify-between rounded-lg bg-gradient-to-r from-foreground/8 to-foreground/3 px-4 py-3">
          <span className="text-[13px] font-medium text-foreground/90 leading-snug">{verdict}</span>
          {entryZoneVnd != null && (
            <span className="text-xs text-muted-foreground/70 shrink-0 ml-4 font-mono">
              Entry {formatPriceVnd(entryZoneVnd / 1000)}
              {entryProximity && (
                <span className={cn('ml-1.5 font-medium', entryProximity.colorClass)}>
                  · {Math.abs(entryProximity.distancePct).toFixed(1)}% {entryProximity.isInZone ? 'below' : 'above'}
                </span>
              )}
            </span>
          )}
        </div>
      )}

      {/* ── Level 2: Section Previews ─────────────────────────────── */}
      {signalCards.length > 0 && (
        <div className="grid grid-cols-2 gap-2">
          {signalCards.map((card) => (
            <div key={card.key} className="rounded-lg bg-muted/8 p-2.5 min-w-0">
              <div className="text-[10px] text-muted-foreground/50 uppercase tracking-wider mb-1">
                {card.label}
              </div>
              <div className="text-[11px] text-foreground/60 leading-relaxed line-clamp-2">
                {card.value}{card.detail ? ` ${card.detail}` : ''}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Level 2: Risks + Flags ────────────────────────────────── */}
      {(riskItems.length > 0 || reviewFlags.length > 0) && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground/50 uppercase tracking-wider">
              <AlertTriangle className="h-3 w-3" /> Key Risks
            </div>
            {reviewFlags.length > 0 && <ReviewFlags flags={reviewFlags} />}
          </div>
          {riskItems.map((risk, index) => (
            <div key={index} className={cn('flex gap-2.5 rounded-lg px-3 py-2.5', RISK_INTENSITY[index] ?? RISK_INTENSITY[4])}>
              <span className="text-rose-400/50 font-mono text-[10px] shrink-0 mt-0.5">{index + 1}</span>
              <p className="text-[13px] text-foreground/80 leading-snug">{risk}</p>
            </div>
          ))}
        </div>
      )}

      {/* ── Level 3: Individual section accordions ─────────────── */}
      {(thesis || proseSections.length > 0) && (
        <div>
          {[
            thesis ? { key: 'thesis' as const, content: thesis } : null,
            ...proseSections.map((key) => ({ key, content: research.sections[key]! })),
          ].filter(Boolean).map((section) => {
            const { key, content } = section!
            const isExpanded = expandedSections.has(key)
            return (
              <div key={key} className="border-t border-border/6">
                <button type="button" onClick={() => toggleSection(key)}
                  className="flex items-center gap-2 w-full py-2.5 text-xs text-muted-foreground/50 hover:text-muted-foreground/80 transition-colors cursor-pointer">
                  <ChevronRight className={cn(
                    'h-3 w-3 shrink-0 transition-transform duration-150',
                    isExpanded && 'rotate-90',
                  )} />
                  {SECTION_LABEL[key as ResearchSectionKey] ?? key}
                </button>
                {isExpanded && (
                  <div className="pb-5 pl-5">
                    <Prose content={content} />
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* ── Metadata ──────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 text-[11px] text-muted-foreground/60">
        <span className="flex items-center gap-1">
          <Calendar className="h-3 w-3" />
          {new Date(research.research_date).toLocaleDateString('en-GB', {
            day: '2-digit', month: 'short', year: 'numeric',
          })}
        </span>
        <span className="rounded bg-muted/40 px-1.5 py-0 font-mono">v{research.version}</span>
        {research.auto_generated && (
          <span className="flex items-center gap-1"><Bot className="h-3 w-3" /> Auto-generated</span>
        )}
      </div>
    </div>
  )
}

// ─── Sub-components ─────────────────────────────────────────────────────────

/** Reference-grade prose — sized for reading, not scanning. */
function Prose({ content }: { content: string }) {
  return (
    <div className="text-[13px] text-foreground/50 leading-[1.75]">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
        table: (props) => <table className="w-full text-xs border-collapse" {...props} />,
        thead: (props) => <thead className="border-b border-border/40" {...props} />,
        th: (props) => <th className="py-1 pr-3 text-left font-semibold text-muted-foreground" {...props} />,
        td: (props) => <td className="py-0.5 pr-3 align-top" {...props} />,
        tr: (props) => <tr className="border-b border-border/20 last:border-0" {...props} />,
        strong: (props) => <strong className="font-medium text-foreground/70" {...props} />,
        p: (props) => <p className="mb-3 last:mb-0" {...props} />,
        ul: (props) => <ul className="list-disc list-outside pl-4 space-y-1 mb-3" {...props} />,
        li: (props) => <li className="pl-0.5" {...props} />,
      }}>{content}</ReactMarkdown>
    </div>
  )
}
