/**
 * ConfirmDialog — reusable confirmation modal for destructive actions.
 */

interface Props {
  open: boolean
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({ open, title, message, confirmLabel = 'Delete', cancelLabel = 'Cancel', danger = true, onConfirm, onCancel }: Props) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onCancel} />
      <div className="relative bg-canvas-surface border border-canvas-border rounded-xl shadow-2xl w-full max-w-sm mx-4 p-5">
        <h3 className="text-sm font-bold text-slate-100 mb-2">{title}</h3>
        <p className="text-[12px] text-slate-400 leading-relaxed mb-5">{message}</p>
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="text-[12px] px-4 py-2 border border-canvas-border text-slate-300 rounded-lg hover:border-slate-500 transition-colors"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            className={`text-[12px] px-4 py-2 rounded-lg font-medium transition-colors ${
              danger
                ? 'bg-status-fail/90 text-white hover:bg-status-fail'
                : 'bg-canvas-accent text-white hover:bg-canvas-accent/80'
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
