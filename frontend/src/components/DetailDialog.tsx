import { useEffect, useRef, type ReactNode } from "react";
import Icon from "@leafygreen-ui/icon";
import IconButton from "@leafygreen-ui/icon-button";
export function DetailDialog({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const node = ref.current;
    node?.showModal();
    return () => node?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className="detail-dialog"
      aria-labelledby="detail-title"
      onCancel={onClose}
      onClick={(event) => {
        if (event.target === ref.current) {
          const bounds = ref.current.getBoundingClientRect();
          if (
            event.clientX < bounds.left ||
            event.clientX > bounds.right ||
            event.clientY < bounds.top ||
            event.clientY > bounds.bottom
          )
            onClose();
        }
      }}
    >
      <header className="detail-heading">
        <h2 id="detail-title">{title}</h2>
        <IconButton aria-label="Close detail panel" onClick={onClose}>
          <Icon aria-hidden glyph="X" />
        </IconButton>
      </header>
      <div className="detail-body">{children}</div>
    </dialog>
  );
}
