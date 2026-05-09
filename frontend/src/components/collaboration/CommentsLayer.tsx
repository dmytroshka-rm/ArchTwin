/**
 * CommentsLayer — Section 10.1
 * Comments anchor to stable semantic IDs (component/relation/layer),
 * NOT screen coordinates.  If a node moves, the comment stays attached.
 *
 * Approval states: draft → review_requested → changes_requested →
 *                  approved_for_pr → promoted → archived
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { commentsApi } from '@/api/endpoints'
import type { CanvasComment, CommentTargetType } from '@/generated/canvas-operation.types'

interface Props {
  layerId: string
  /** Optional: filter to a specific target */
  targetId?: string
  targetType?: CommentTargetType
}

export function CommentsLayer({ layerId, targetId, targetType }: Props) {
  const qc = useQueryClient()
  const [draft, setDraft] = useState('')
  const [authorName] = useState('current-user')   // In a real app: from auth context

  const { data: comments = [] } = useQuery({
    queryKey: ['comments', layerId],
    queryFn: () => commentsApi.list(layerId),
  })

  const filtered = targetId
    ? comments.filter((c) => c.anchor.target_id === targetId)
    : comments

  const createMutation = useMutation({
    mutationFn: (body: string) =>
      commentsApi.create(layerId, {
        anchor: {
          target_type: targetType ?? 'layer',
          target_id:   targetId ?? layerId,
          layer_id:    layerId,
        },
        author:   authorName,
        body,
        resolved: false,
      }),
    onSuccess: () => {
      setDraft('')
      qc.invalidateQueries({ queryKey: ['comments', layerId] })
    },
  })

  const resolveMutation = useMutation({
    mutationFn: (commentId: string) => commentsApi.resolve(layerId, commentId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['comments', layerId] }),
  })

  return (
    <div className="flex flex-col text-sm">
      <PanelHeader title="Comments" count={filtered.filter((c) => !c.resolved).length} />

      {/* Comment list */}
      <div className="flex flex-col gap-2 p-3">
        {filtered.length === 0 && (
          <p className="text-[11px] text-slate-500">No comments yet.</p>
        )}
        {filtered.map((comment) => (
          <CommentCard
            key={comment.id}
            comment={comment}
            onResolve={() => resolveMutation.mutate(comment.id)}
          />
        ))}
      </div>

      {/* Add comment */}
      <div className="px-3 pb-3 flex flex-col gap-1.5">
        <textarea
          className="w-full bg-canvas-bg border border-canvas-border rounded-md px-2 py-1.5 text-xs text-slate-200 resize-none focus:border-canvas-accent outline-none"
          rows={3}
          placeholder="Add a comment anchored to this component…"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <button
          disabled={!draft.trim() || createMutation.isPending}
          onClick={() => createMutation.mutate(draft.trim())}
          className={clsx(
            'self-end text-xs px-3 py-1 rounded border',
            draft.trim()
              ? 'border-canvas-accent text-canvas-accent hover:bg-canvas-accent/10'
              : 'border-canvas-border text-slate-600 cursor-not-allowed',
          )}
        >
          {createMutation.isPending ? 'Posting…' : 'Post'}
        </button>
      </div>
    </div>
  )
}

// ── CommentCard ────────────────────────────────────────────────────────────

function CommentCard({ comment, onResolve }: { comment: CanvasComment; onResolve: () => void }) {
  return (
    <div className={clsx(
      'rounded-md border px-2.5 py-2',
      comment.resolved
        ? 'border-canvas-border/30 opacity-50'
        : 'border-canvas-border',
    )}>
      <div className="flex items-center gap-1.5 mb-1">
        <span className="text-[10px] font-semibold text-canvas-accent">{comment.author}</span>
        <span className="text-[10px] text-slate-600 ml-auto">
          {new Date(comment.created_at).toLocaleString()}
        </span>
      </div>

      {/* Anchor info */}
      <div className="flex items-center gap-1 mb-1">
        <span className={clsx(
          'text-[9px] font-mono px-1 rounded',
          comment.anchor.target_type === 'component' ? 'bg-canvas-accent/10 text-canvas-accent' :
          comment.anchor.target_type === 'relation'  ? 'bg-status-info/10 text-status-info' :
          'bg-canvas-border/50 text-slate-500',
        )}>
          {comment.anchor.target_type}:{comment.anchor.target_id.slice(-8)}
        </span>
        {comment.anchor.field_path && (
          <span className="text-[9px] font-mono text-slate-600">.{comment.anchor.field_path}</span>
        )}
      </div>

      <p className="text-xs text-slate-300 leading-relaxed">{comment.body}</p>

      {!comment.resolved && (
        <button
          onClick={onResolve}
          className="mt-1.5 text-[10px] text-slate-500 hover:text-status-pass"
        >
          Resolve ✓
        </button>
      )}
      {comment.resolved && (
        <span className="text-[10px] text-status-pass mt-1.5 inline-block">Resolved</span>
      )}
    </div>
  )
}

function PanelHeader({ title, count }: { title: string; count: number }) {
  return (
    <div className="px-3 py-2 border-b border-canvas-border flex items-center gap-2">
      <span className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold flex-1">{title}</span>
      {count > 0 && (
        <span className="text-[10px] font-mono bg-canvas-accent/20 text-canvas-accent rounded px-1">{count}</span>
      )}
    </div>
  )
}
